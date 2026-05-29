import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.policy import Policy
from apps.api.schemas.policy import PolicyCreate


async def create_policy(db: AsyncSession, data: PolicyCreate) -> Policy:
    existing = await db.execute(select(Policy).where(Policy.code == data.code))
    if existing.scalar_one_or_none() is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="制度编码已存在")

    policy = Policy(
        code=data.code,
        title=data.title,
        owner_department=data.owner_department,
        category=data.category or "",
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(db: AsyncSession) -> list[Policy]:
    result = await db.execute(select(Policy).order_by(Policy.created_at.desc()))
    return list(result.scalars().all())


async def get_policy(db: AsyncSession, policy_id: uuid.UUID) -> Policy | None:
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    return result.scalar_one_or_none()
