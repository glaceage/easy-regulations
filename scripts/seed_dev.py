#!/usr/bin/env python3
"""Seed development database with sample users, policy, and revision."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import get_settings
from apps.api.models.policy import Policy, PolicyStatus, PolicyVersion
from apps.api.models.revision import Revision, RevisionState
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole
from apps.api.services.storage import StorageService

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEV_PASSWORD = "dev123"

USERS: list[dict[str, object]] = [
    {
        "username": "admin",
        "display_name": "制度管理员",
        "department": "合规部",
        "role": UserRole.POLICY_ADMIN,
    },
    {
        "username": "owner1",
        "display_name": "经办人",
        "department": "人力部",
        "role": UserRole.OWNER,
    },
    {
        "username": "reviewer1",
        "display_name": "审核人",
        "department": "法务部",
        "role": UserRole.REVIEWER,
    },
]

POLICY_CODE = "HR-001"
POLICY_TITLE = "考勤管理办法"
CHANGE_BRIEF = "根据2026年劳动法修订及公司组织调整，更新年假计算规则与远程办公考勤要求。"

PUBLISHED_MD = """# 考勤管理办法

## 第一章 总则

第一条 为规范公司员工考勤管理，特制定本办法。

## 第二章 工作时间

第二条 标准工作时间为周一至周五 9:00-18:00。
"""

DRAFT_MD = """# 考勤管理办法（修订草案）

## 第一章 总则

第一条 为规范公司员工考勤管理，特制定本办法。

## 第二章 工作时间

第二条 标准工作时间为周一至周五 9:00-18:00。支持弹性工作制。

## 第三章 年假

第三条 工作满一年享受带薪年假 5 天，满三年 10 天。
"""


def _put_object(storage: StorageService, key: str, data: bytes) -> str:
    content_sha256 = hashlib.sha256(data).hexdigest()
    storage._client.put_object(
        Bucket=storage._settings.minio_bucket,
        Key=key,
        Body=data,
        Metadata={"content-sha256": content_sha256},
    )
    return content_sha256


async def _ensure_users(session: AsyncSession) -> dict[str, User]:
    user_map: dict[str, User] = {}
    for spec in USERS:
        username = str(spec["username"])
        result = await session.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing is not None:
            user_map[username] = existing
            print(f"  用户已存在: {username}")
            continue

        user = User(
            username=username,
            display_name=str(spec["display_name"]),
            department=str(spec["department"]),
            role=spec["role"],  # type: ignore[arg-type]
            password_hash=pwd.hash(DEV_PASSWORD),
        )
        session.add(user)
        await session.flush()
        user_map[username] = user
        print(f"  创建用户: {username} ({user.role.value})，密码: {DEV_PASSWORD}")
    return user_map


async def _ensure_sample_policy(
    session: AsyncSession,
    user_map: dict[str, User],
    storage: StorageService,
) -> None:
    result = await session.execute(select(Policy).where(Policy.code == POLICY_CODE))
    policy = result.scalar_one_or_none()
    if policy is not None:
        print(f"  制度已存在: {POLICY_CODE}")
        await _ensure_consultation_demo(session, user_map, policy, storage)
        return

    policy = Policy(
        code=POLICY_CODE,
        title=POLICY_TITLE,
        category="人力资源",
        owner_department="人力部",
    )
    session.add(policy)
    await session.flush()

    published_bytes = PUBLISHED_MD.encode("utf-8")
    published_sha256 = hashlib.sha256(published_bytes).hexdigest()
    published_key = storage.put_bytes(
        published_bytes,
        suffix=".md",
        prefix=f"policies/{policy.id}/versions/",
    )

    version = PolicyVersion(
        policy_id=policy.id,
        version_label="v1.0",
        status=PolicyStatus.ACTIVE,
        effective_date=date(2025, 1, 1),
        markdown_key=published_key,
        content_sha256=published_sha256,
        section_tree={"sections": []},
        published_by_id=user_map["admin"].id,
    )
    session.add(version)
    await session.flush()
    policy.current_version_id = version.id

    revision_id = uuid.uuid4()
    draft_bytes = DRAFT_MD.encode("utf-8")
    draft_key = f"drafts/{revision_id}.md"
    draft_sha256 = _put_object(storage, draft_key, draft_bytes)

    revision = Revision(
        id=revision_id,
        policy_id=policy.id,
        base_version_id=version.id,
        owner_user_id=user_map["owner1"].id,
        state=RevisionState.DRAFT,
        change_brief=CHANGE_BRIEF,
        draft_markdown_key=draft_key,
        draft_content_sha256=draft_sha256,
        target_version_label="v2.0",
    )
    session.add(revision)
    print(f"  创建制度: {POLICY_CODE}（v1.0 已发布 + 草稿修订 v2.0）")
    await _ensure_consultation_demo(session, user_map, policy, storage)


async def _ensure_consultation_demo(
    session: AsyncSession,
    user_map: dict[str, User],
    policy: Policy,
    storage: StorageService,
) -> None:
    """Ensure a revision in consultation with reviewer1 assigned for demo."""
    result = await session.execute(
        select(Revision).where(
            Revision.policy_id == policy.id,
            Revision.state == RevisionState.IN_CONSULTATION,
        )
    )
    consultation = result.scalar_one_or_none()
    if consultation is None:
        revision_id = uuid.uuid4()
        draft_bytes = DRAFT_MD.encode("utf-8")
        draft_key = f"drafts/{revision_id}.md"
        draft_sha256 = _put_object(storage, draft_key, draft_bytes)
        consultation = Revision(
            id=revision_id,
            policy_id=policy.id,
            base_version_id=policy.current_version_id,
            owner_user_id=user_map["owner1"].id,
            state=RevisionState.IN_CONSULTATION,
            change_brief=CHANGE_BRIEF,
            draft_markdown_key=draft_key,
            draft_content_sha256=draft_sha256,
            target_version_label="v2.0-征求",
        )
        session.add(consultation)
        await session.flush()
        print("  创建征求意见示例修订: v2.0-征求（in_consultation）")

    reviewer = user_map.get("reviewer1")
    if reviewer is None:
        return

    existing = await session.execute(
        select(RevisionReviewer).where(
            RevisionReviewer.revision_id == consultation.id,
            RevisionReviewer.user_id == reviewer.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(
            RevisionReviewer(
                revision_id=consultation.id,
                user_id=reviewer.id,
                is_mandatory=True,
                assigned_by_id=user_map["owner1"].id,
                note="多部门征求意见示例",
            )
        )
        print("  已指定 reviewer1 为 v2.0-征求 的必反馈评审人")


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    storage = StorageService()

    async with session_factory() as session:
        user_map = await _ensure_users(session)
        await _ensure_sample_policy(session, user_map, storage)
        await session.commit()

    await engine.dispose()


def main() -> None:
    print("正在写入开发种子数据...")
    asyncio.run(seed())
    print("开发数据种子完成。")


if __name__ == "__main__":
    main()
