from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas.ops import DeadLetterListResponse, DeadLetterRetryResponse
from app.services import dead_letter_service

router = APIRouter(
    prefix="/dead-letter", tags=["dead-letter"], dependencies=[Depends(require_api_key)]
)


@router.get("", response_model=DeadLetterListResponse)
async def list_dead_letter_jobs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> DeadLetterListResponse:
    return await dead_letter_service.list_dead_letter_jobs(db, page, page_size)


@router.post("/{dead_letter_id}/retry", response_model=DeadLetterRetryResponse)
async def retry_dead_letter_job(
    dead_letter_id: str, db: AsyncSession = Depends(get_db)
) -> DeadLetterRetryResponse:
    return await dead_letter_service.retry_dead_letter_job(db, dead_letter_id)
