"""Mountable FastAPI router; the host platform supplies its own auth dependency."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from edge_reasoner.integration import EdgeFacade

logger = logging.getLogger(__name__)


class EdgeRunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=16000)
    image_base64: str | None = None
    allow_cloud_fallback: bool = False


def create_edge_router(authorize: Callable, *, facade: EdgeFacade | None = None) -> APIRouter:
    """Use create_edge_router(current_tenant) so host auth applies to every route."""
    service = facade or EdgeFacade()
    router = APIRouter(prefix="/v1/edge", tags=["Edge Reasoner"], dependencies=[Depends(authorize)])

    @router.get("/status")
    def status() -> dict:
        return service.status()

    @router.get("/evaluation")
    def evaluation() -> dict:
        report = service.evaluation()
        if report is None:
            raise HTTPException(404, "No observed evaluation is available")
        return report

    @router.get("/backtest")
    def backtest() -> dict:
        report = service.backtest()
        if report is None:
            raise HTTPException(404, "No observed backtest is available")
        return report

    @router.post("/run")
    async def run(request: EdgeRunRequest) -> dict:
        image = None
        if request.image_base64 is not None:
            if len(request.image_base64) > 14 * 1024 * 1024:
                raise HTTPException(413, "Image exceeds 10 MB")
            try:
                image = base64.b64decode(request.image_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(422, "Invalid base64 image") from exc
        try:
            return await asyncio.to_thread(
                service.run,
                request.question,
                image=image,
                allow_cloud_fallback=request.allow_cloud_fallback,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            logger.error("Edge Reasoner failed (%s)", type(exc).__name__)
            raise HTTPException(
                503, "Edge Reasoner unavailable; check local model configuration"
            ) from exc

    return router
