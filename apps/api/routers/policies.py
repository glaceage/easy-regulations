import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.policy import PolicyCreate, PolicyResponse
from apps.api.services import policies as policy_service
from apps.api.services.auth import get_current_user

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.post("", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    policy = await policy_service.create_policy(db, body)
    return policy


@router.get("", response_model=list[PolicyResponse])
async def list_policies(db: AsyncSession = Depends(get_db)):
    return await policy_service.list_policies(db)


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    policy = await policy_service.get_policy(db, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="制度不存在")
    return policy
