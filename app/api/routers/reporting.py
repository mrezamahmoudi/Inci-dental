"""Thin reporting and action-item HTTP handlers."""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from api.routers.incident import authenticate
from application.reporting.commands import IntegrationDisabledError
from domain.reporting.ports import IncidentReport
from infrastructure.http_client import ExternalServiceError

router = APIRouter(prefix="/api/v1", tags=["Reports and actions"])
logger = logging.getLogger(__name__)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class IncidentReportRequest(BaseModel):
    title: ShortText
    summary: NonEmptyText
    impact: NonEmptyText
    root_cause: NonEmptyText
    timeline: NonEmptyText
    resolution: NonEmptyText


class IncidentReportResponse(BaseModel):
    provider: str
    report_id: str
    title: str
    url: str


class ActionItemRequest(BaseModel):
    description: NonEmptyText
    assignee: ShortText = Field(
        description="Assignee identifier understood by the configured action provider."
    )
    priority: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    related_report_id: ShortText
    related_report_provider: str | None = Field(
        default=None,
        description="Optional report provider override; defaults to REPORT_PROVIDER.",
    )
    title: ShortText | None = Field(
        default=None, description="Optional action summary; defaults to the description's first line."
    )


class ActionItemResponse(BaseModel):
    issue_id: str
    issue_key: str
    url: str
    assignee: str
    priority: str
    related_report_id: str
    remote_link_id: str


def _upstream_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ExternalServiceError):
        logger.error("%s integration failed with HTTP %s", exc.service, exc.status_code)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The reporting or issue-tracking service rejected the request.",
    )


@router.post(
    "/incident-reports", response_model=IncidentReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_incident_report(
    payload: IncidentReportRequest, request: Request,
    username: Annotated[str, Depends(authenticate)],
) -> dict:
    report = IncidentReport(
        title=payload.title, summary=payload.summary, impact=payload.impact,
        root_cause=payload.root_cause, timeline=payload.timeline,
        resolution=payload.resolution, created_by=username,
        created_at=datetime.now(timezone.utc),
    )
    try:
        result = await request.app.state.create_incident_report.execute(report)
    except IntegrationDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (ExternalServiceError, KeyError, ValueError) as exc:
        raise _upstream_error(exc) from exc
    logger.info("Incident report %s created by %s", result["report_id"], username)
    return result


@router.post(
    "/actions", response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action_item(
    payload: ActionItemRequest, request: Request,
    username: Annotated[str, Depends(authenticate)],
) -> dict:
    try:
        result = await request.app.state.create_action_item.execute(
            description=payload.description, assignee=payload.assignee,
            priority=payload.priority, related_report_id=payload.related_report_id,
            title=payload.title or "", report_provider=payload.related_report_provider,
        )
    except IntegrationDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ExternalServiceError, KeyError) as exc:
        raise _upstream_error(exc) from exc
    logger.info(
        "Action %s linked to report %s by %s",
        result["issue_key"], payload.related_report_id, username,
    )
    return result
