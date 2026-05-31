"""Standalone end-to-end probe of the revision workflow across roles.

Drives the real FastAPI app over ASGI with an in-memory SQLite DB and a
stubbed object storage, exercising owner -> reviewer -> admin and probing
known gap candidates. Prints PASS/FAIL/⚠ lines so we can build a report.

Run: python scripts/e2e_probe.py
"""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.db.session import get_db
from apps.api.main import create_app
from apps.api.models.audit import AuditEvent
from apps.api.models.base import Base
from apps.api.models.comment import Comment
from apps.api.models.llm_suggestion import LlmSuggestion
from apps.api.models.policy import Policy, PolicyVersion
from apps.api.models.revision import Revision
from apps.api.models.revision_reviewer import RevisionReviewer
from apps.api.models.user import User, UserRole

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

TABLES = [
    User.__table__,
    Policy.__table__,
    PolicyVersion.__table__,
    Revision.__table__,
    RevisionReviewer.__table__,
    Comment.__table__,
    LlmSuggestion.__table__,
    AuditEvent.__table__,
]

results: list[tuple[str, str, str]] = []


def record(tag: str, name: str, detail: str = "") -> None:
    results.append((tag, name, detail))
    print(f"{tag:4} | {name} {('- ' + detail) if detail else ''}")


def _patch_jsonb() -> None:
    for table in TABLES:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


def make_storage():
    storage = MagicMock()
    store: dict[str, bytes] = {}

    def put_object(key, data):
        store[key] = data
        return key

    def put_bytes(data, suffix, prefix=""):
        key = f"{prefix}{uuid.uuid4()}{suffix}"
        store[key] = data
        return key

    def get_bytes(key):
        if key not in store:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return store[key]

    storage.put_object.side_effect = put_object
    storage.put_bytes.side_effect = put_bytes
    storage.get_bytes.side_effect = get_bytes
    storage.last_sha256 = "abc123"
    return storage


async def login(ac: AsyncClient, username: str) -> str:
    r = await ac.post("/api/auth/login", json={"username": username, "password": "secret"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def main() -> None:
    _patch_jsonb()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))

    async with session_factory() as session:
        for username, role, dept in [
            ("owner1", UserRole.OWNER, "人力部"),
            ("owner2", UserRole.OWNER, "人力部"),
            ("reviewer1", UserRole.REVIEWER, "法务部"),
            ("reviewer2", UserRole.REVIEWER, "财务部"),
            ("admin", UserRole.POLICY_ADMIN, "总办"),
            ("sysadmin", UserRole.SYS_ADMIN, "IT"),
            ("reader1", UserRole.READER, "行政部"),
        ]:
            session.add(
                User(
                    username=username,
                    display_name=username,
                    department=dept,
                    role=role,
                    password_hash=pwd.hash("secret"),
                )
            )
        await session.commit()

    app = create_app()

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    storage = make_storage()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    with patch("apps.api.services.revisions.StorageService", return_value=storage), patch(
        "apps.api.services.ai.StorageService", return_value=storage
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            t_owner = await login(ac, "owner1")
            t_owner2 = await login(ac, "owner2")
            t_rev1 = await login(ac, "reviewer1")
            t_rev2 = await login(ac, "reviewer2")
            t_admin = await login(ac, "admin")
            t_sys = await login(ac, "sysadmin")
            t_reader = await login(ac, "reader1")

            print("\n========== A. RBAC on creation ==========")
            # reader creates a policy?
            r = await ac.post(
                "/api/policies",
                json={"code": "RD-001", "title": "读者越权", "owner_department": "行政部"},
                headers=hdr(t_reader),
            )
            if r.status_code == 201:
                record("BUG", "reader can create policy (no role guard)", f"HTTP {r.status_code}")
            else:
                record("OK", "reader blocked from creating policy", f"HTTP {r.status_code}")

            # public list policies (no auth header)
            r = await ac.get("/api/policies")
            if r.status_code == 200:
                record("BUG", "GET /api/policies is public (no auth required)", f"HTTP {r.status_code}")
            else:
                record("OK", "policy list requires auth", f"HTTP {r.status_code}")

            print("\n========== B. Owner happy path ==========")
            r = await ac.post(
                "/api/policies",
                json={"code": "HR-100", "title": "考勤办法", "owner_department": "人力部"},
                headers=hdr(t_owner),
            )
            assert r.status_code == 201, r.text
            policy_id = r.json()["id"]
            record("OK", "owner created policy", policy_id[:8])

            r = await ac.post(
                "/api/revisions",
                json={
                    "policy_id": policy_id,
                    "change_brief": "依据新劳动法调整年假与考勤口径",
                    "target_version_label": "v2.0",
                },
                headers=hdr(t_owner),
            )
            assert r.status_code == 201, r.text
            rev_id = r.json()["id"]
            record("OK", "owner created revision (draft)", rev_id[:8])

            # BUG-3 remediation: owner can patch version label later
            r = await ac.patch(
                f"/api/revisions/{rev_id}",
                json={"target_version_label": "v2.0"},
                headers=hdr(t_owner),
            )
            record("OK" if r.status_code == 200 else "BUG", "owner can PATCH target_version_label", f"HTTP {r.status_code}")

            print("\n========== C. Pre-assign reviewer in draft ==========")
            # backend says assignable in draft; UI only allows in consultation
            r = await ac.get("/api/policies", headers=hdr(t_owner))  # warm
            # need reviewer user id; list via assignment attempt
            # fetch reviewer ids through DB
            async with session_factory() as s:
                from sqlalchemy import select

                rev1 = (await s.execute(select(User).where(User.username == "reviewer1"))).scalar_one()
                rev2 = (await s.execute(select(User).where(User.username == "reviewer2"))).scalar_one()
                reader = (await s.execute(select(User).where(User.username == "reader1"))).scalar_one()
                rev1_id, rev2_id, reader_id = str(rev1.id), str(rev2.id), str(reader.id)

            r = await ac.post(
                f"/api/revisions/{rev_id}/reviewers",
                json={"username": "reviewer1", "is_mandatory": True},
                headers=hdr(t_owner),
            )
            if r.status_code in (200, 201):
                record("OK", "owner pre-assigned mandatory reviewer in draft", f"HTTP {r.status_code}")
            else:
                record("INFO", "pre-assign in draft rejected", f"HTTP {r.status_code} {r.text[:80]}")

            # try assigning a reader as reviewer
            r = await ac.post(
                f"/api/revisions/{rev_id}/reviewers",
                json={"username": "reader1", "is_mandatory": False},
                headers=hdr(t_owner),
            )
            if r.status_code in (200, 201):
                record("BUG", "non-reviewer (reader) assignable as reviewer", f"HTTP {r.status_code}")
            else:
                record("OK", "reader rejected as reviewer", f"HTTP {r.status_code}")

            print("\n========== D. Submit to consultation, reviewer flow ==========")
            r = await ac.post(
                f"/api/revisions/{rev_id}/transition",
                json={"target_state": "in_consultation"},
                headers=hdr(t_owner),
            )
            assert r.status_code == 200, r.text
            record("OK", "owner -> in_consultation", r.json()["state"])

            # reviewer2 not assigned: can they comment?
            r = await ac.post(
                f"/api/revisions/{rev_id}/comments",
                json={"section_id": "intro", "section_title": "总则", "body": "未分配也来评论"},
                headers=hdr(t_rev2),
            )
            if r.status_code in (200, 201):
                record("BUG", "unassigned reviewer can comment", f"HTTP {r.status_code}")
            else:
                record("OK", "unassigned reviewer blocked from commenting", f"HTTP {r.status_code}")

            # assigned reviewer1 comments
            r = await ac.post(
                f"/api/revisions/{rev_id}/comments",
                json={"section_id": "intro", "section_title": "总则", "body": "建议明确弹性工时定义"},
                headers=hdr(t_rev1),
            )
            assert r.status_code in (200, 201), r.text
            comment_id = r.json()["id"]
            record("OK", "assigned reviewer commented", comment_id[:8])

            print("\n========== E. IDOR / read authorization ==========")
            # reviewer2 (not assigned) reads the draft markdown
            r = await ac.get(f"/api/revisions/{rev_id}/draft-markdown", headers=hdr(t_rev2))
            if r.status_code == 200:
                record("BUG", "unassigned reviewer reads draft markdown (IDOR)", f"HTTP {r.status_code}")
            else:
                record("OK", "draft read blocked for unassigned", f"HTTP {r.status_code}")

            # reader reads comments
            r = await ac.get(f"/api/revisions/{rev_id}/comments", headers=hdr(t_reader))
            if r.status_code == 200:
                record("BUG", "reader can list all comments (IDOR)", f"HTTP {r.status_code}")
            else:
                record("OK", "comment list restricted", f"HTTP {r.status_code}")

            # owner2 (different owner) reads/edits this revision
            r = await ac.get(f"/api/revisions/{rev_id}/draft-markdown", headers=hdr(t_owner2))
            tag = "BUG" if r.status_code == 200 else "OK"
            record(tag, "other-owner reads draft markdown", f"HTTP {r.status_code}")

            r = await ac.put(
                f"/api/revisions/{rev_id}/draft-markdown",
                json={"markdown": "# 恶意覆盖\n", "change_summary": "x"},
                headers=hdr(t_owner2),
            )
            if r.status_code in (200, 201):
                record("BUG", "other-owner can OVERWRITE draft of foreign revision", f"HTTP {r.status_code}")
            else:
                record("OK", "other-owner cannot edit foreign draft", f"HTTP {r.status_code}")

            print("\n========== F. Consultation close WITHOUT mandatory feedback ==========")
            # Create a 2nd mandatory reviewer who will NOT comment, then close consultation.
            r = await ac.post(
                f"/api/revisions/{rev_id}/reviewers",
                json={"username": "reviewer2", "is_mandatory": True},
                headers=hdr(t_owner),
            )
            record("INFO", "added 2nd mandatory reviewer (reviewer2, no comment)", f"HTTP {r.status_code}")

            r = await ac.post(
                f"/api/revisions/{rev_id}/transition",
                json={"target_state": "in_revision"},
                headers=hdr(t_owner),
            )
            if r.status_code == 200:
                record("BUG", "consultation closed though mandatory reviewer2 gave no feedback", "HTTP 200")
            else:
                record("OK", "consultation close gated on mandatory feedback", f"HTTP {r.status_code}")

            print("\n========== G. Publish gate ==========")
            # try submit for publish with an open comment
            r = await ac.post(
                f"/api/revisions/{rev_id}/transition",
                json={"target_state": "pending_publish"},
                headers=hdr(t_owner),
            )
            if r.status_code != 200:
                record("OK", "pending_publish blocked (open comment / missing feedback)", f"HTTP {r.status_code}")
            else:
                record("WARN", "pending_publish allowed with open comment", "HTTP 200")

            # resolve the open comment as rejected WITHOUT resolution note
            r = await ac.patch(
                f"/api/comments/{comment_id}",
                json={"status": "rejected"},
                headers=hdr(t_owner),
            )
            if r.status_code == 500:
                record("BUG", "reject w/o note -> HTTP 500 (status var shadows fastapi.status)", f"HTTP {r.status_code}")
            elif r.status_code in (200, 201):
                record("BUG", "comment rejected with EMPTY resolution_note", f"HTTP {r.status_code}")
            else:
                record("OK", "reject requires resolution_note", f"HTTP {r.status_code}")

            # resolve properly
            r = await ac.patch(
                f"/api/comments/{comment_id}",
                json={"status": "accepted", "resolution_note": "已采纳并补充定义"},
                headers=hdr(t_owner),
            )
            record("INFO", "resolve comment accepted", f"HTTP {r.status_code}")

            # reviewer2 still no comment -> publish gate should still block
            r = await ac.post(
                f"/api/revisions/{rev_id}/transition",
                json={"target_state": "pending_publish"},
                headers=hdr(t_owner),
            )
            record("INFO", "pending_publish attempt after resolve", f"HTTP {r.status_code} {r.text[:90]}")
            if r.status_code != 200:
                # give reviewer2 a comment then retry
                await ac.post(
                    f"/api/revisions/{rev_id}/transition",
                    json={"target_state": "in_consultation"},
                    headers=hdr(t_owner),
                )
                await ac.post(
                    f"/api/revisions/{rev_id}/comments",
                    json={"section_id": "intro", "section_title": "总则", "body": "无意见"},
                    headers=hdr(t_rev2),
                )
                await ac.post(
                    f"/api/revisions/{rev_id}/transition",
                    json={"target_state": "in_revision"},
                    headers=hdr(t_owner),
                )
                # resolve reviewer2's comment
                async with session_factory() as s:
                    from sqlalchemy import select

                    c2 = (
                        await s.execute(
                            select(Comment).where(Comment.author_id == uuid.UUID(rev2_id))
                        )
                    ).scalars().first()
                    c2_id = str(c2.id)
                await ac.patch(
                    f"/api/comments/{c2_id}",
                    json={"status": "accepted", "resolution_note": "知悉"},
                    headers=hdr(t_owner),
                )
                r = await ac.post(
                    f"/api/revisions/{rev_id}/transition",
                    json={"target_state": "pending_publish"},
                    headers=hdr(t_owner),
                )
                record("INFO", "pending_publish after full feedback", f"HTTP {r.status_code} {r.text[:90]}")

            print("\n========== H. Remove mandatory reviewer after gate ==========")
            rl = await ac.get(f"/api/revisions/{rev_id}/reviewers", headers=hdr(t_owner))
            assignment_id = None
            if rl.status_code == 200:
                for a in rl.json():
                    if a.get("username") == "reviewer2":
                        assignment_id = a["id"]
            if assignment_id:
                r = await ac.delete(
                    f"/api/revisions/{rev_id}/reviewers/{assignment_id}",
                    headers=hdr(t_owner),
                )
                record(
                    "OK" if r.status_code not in (200, 204) else "WARN",
                    "remove mandatory reviewer while pending_publish (no state guard)",
                    f"HTTP {r.status_code}",
                )
            else:
                record("INFO", "could not resolve reviewer2 assignment id", f"list HTTP {rl.status_code}")

            print("\n========== I. Publish authorization ==========")
            # owner cannot publish
            r = await ac.post(f"/api/revisions/{rev_id}/publish", headers=hdr(t_owner))
            record("OK" if r.status_code in (401, 403) else "BUG", "owner publish blocked", f"HTTP {r.status_code}")

            # sys_admin publish? (WARN-1 fix: should be authorized)
            r = await ac.post(f"/api/revisions/{rev_id}/publish", headers=hdr(t_sys))
            if r.status_code in (200, 201):
                record("OK", "sys_admin can publish", f"HTTP {r.status_code}")
                published = True
            else:
                record("BUG", "sys_admin CANNOT publish", f"HTTP {r.status_code} {r.text[:80]}")
                published = False

            if not published:
                r = await ac.post(f"/api/revisions/{rev_id}/publish", headers=hdr(t_admin))
                record("OK" if r.status_code in (200, 201) else "BUG", "policy_admin publish", f"HTTP {r.status_code} {r.text[:80]}")

            print("\n========== J. Notifications ==========")
            r = await ac.get("/api/notifications", headers=hdr(t_rev1))
            if r.status_code == 200:
                items = r.json()
                n = len(items) if isinstance(items, list) else len(items.get("items", []))
                anyread = None
                sample = items if isinstance(items, list) else items.get("items", [])
                if sample:
                    anyread = sample[0].get("read")
                record("INFO", f"reviewer notifications count={n}", f"first.read={anyread}")
            else:
                record("WARN", "notifications endpoint error", f"HTTP {r.status_code}")

            # mark read endpoint?
            r = await ac.post("/api/notifications/read", headers=hdr(t_rev1))
            r2 = await ac.patch("/api/notifications/read", headers=hdr(t_rev1))
            if r.status_code in (404, 405) and r2.status_code in (404, 405):
                record("BUG", "no mark-notification-read endpoint", f"POST {r.status_code}/PATCH {r2.status_code}")
            else:
                record("OK", "mark-read endpoint exists", f"POST {r.status_code}/PATCH {r2.status_code}")

            print("\n========== K. Reviewer inbox role lock ==========")
            r = await ac.get("/api/reviews/assignments", headers=hdr(t_admin))
            if r.status_code in (401, 403):
                record("WARN", "policy_admin cannot use reviewer inbox", f"HTTP {r.status_code}")
            else:
                record("INFO", "admin reviewer inbox", f"HTTP {r.status_code}")

            print("\n========== L. Job status graceful degradation ==========")
            r = await ac.get("/api/jobs/does-not-exist-123", headers=hdr(t_reader))
            if r.status_code == 500:
                record("BUG", "job status 500 on bad id / no redis", f"HTTP {r.status_code}")
            else:
                record("OK", "job status degrades gracefully (no 500)", f"HTTP {r.status_code}")

    await engine.dispose()

    print("\n\n================ SUMMARY ================")
    bugs = [r for r in results if r[0] == "BUG"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"BUG: {len(bugs)}  WARN: {len(warns)}  total checks: {len(results)}")
    for tag in ("BUG", "WARN"):
        for t, name, detail in results:
            if t == tag:
                print(f"  [{t}] {name} {('- ' + detail) if detail else ''}")


if __name__ == "__main__":
    asyncio.run(main())
