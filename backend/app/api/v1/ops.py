from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.db.session import get_db
from app.schemas.ops import OpsOverviewResponse
from app.services import ops_service

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_api_key)])


@router.get("/overview", response_model=OpsOverviewResponse)
async def get_overview(db: AsyncSession = Depends(get_db)) -> OpsOverviewResponse:
    return await ops_service.get_overview(db)
