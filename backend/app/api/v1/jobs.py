from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas.ops import JobDetailResponse
from app.services import event_service

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_endpoint(
    job_id: str, db: AsyncSession = Depends(get_db)
) -> JobDetailResponse:
    return await event_service.get_job(db, job_id)
