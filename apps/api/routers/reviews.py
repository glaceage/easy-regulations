from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.session import get_db
from apps.api.models.user import User
from apps.api.schemas.reviewer import ReviewAssignmentResponse
from apps.api.services.auth import get_current_user
from apps.api.services import reviewers as reviewer_service

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/assignments", response_model=list[ReviewAssignmentResponse])
async def list_my_review_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await reviewer_service.list_my_assignments(db, current_user)
