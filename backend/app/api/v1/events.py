from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_key
from app.core.states import EventStatus
from app.db.session import get_db
from app.schemas.event import EventCreateRequest, EventListResponse, EventResponse
from app.services import event_service

router = APIRouter(
    prefix="/events", tags=["events"], dependencies=[Depends(require_api_key)]
)


@router.post("", response_model=EventResponse, status_code=201)
async def create_event_endpoint(
    payload: EventCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """
    Persists the event and creates one notification_job per requested
    channel, transactionally. Does NOT perform delivery — that happens
    asynchronously once workers land in Phase 3.
    """
    return await event_service.create_event(db, payload)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_endpoint(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    return await event_service.get_event(db, event_id)


@router.get("", response_model=EventListResponse)
async def list_events_endpoint(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status: EventStatus | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> EventListResponse:
    return await event_service.list_events(db, page, page_size, status, event_type)
