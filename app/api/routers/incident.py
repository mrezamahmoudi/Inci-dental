"""Thin HTTP handlers for incident management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from application.incident.commands import IncidentOperationError
from application.incident.queries import GetIncident
from domain.incident.aggregate import IncidentAlreadyActiveError, NoActiveIncidentError

router = APIRouter(prefix="/api/v1/incidents", tags=["Incidents"])
logger = logging.getLogger(__name__)


class StartIncidentRequest(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] = Field(
        description="Human-readable incident title; also used in the group name."
    )


class IncidentResponse(BaseModel):
    active: bool
    title: str | None = None
    channel_name: str | None = None
    channel_url: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


def authenticate(request: Request) -> str:
    """API-layer authentication only; no incident logic in this dependency."""
    return request.app.state.auth.authenticate(request)


@router.get("/current", response_model=IncidentResponse)
def current_incident(request: Request) -> dict:
    return GetIncident(request.app.state.incident).execute()


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def start_incident(
    payload: StartIncidentRequest, request: Request,
    username: Annotated[str, Depends(authenticate)],
) -> dict:
    try:
        result = await request.app.state.start_incident.execute(payload.title, username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IncidentAlreadyActiveError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IncidentOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    logger.info("Incident started by %s", username)
    request.app.state.record_started(username)
    return result


@router.post("/current/end", response_model=IncidentResponse)
async def end_incident(
    request: Request, username: Annotated[str, Depends(authenticate)],
) -> dict:
    try:
        result = await request.app.state.end_incident.execute(username)
    except NoActiveIncidentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IncidentOperationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    request.app.state.record_ended(username)
    return result
