"""OmniAgent 接入層：模型目錄、路由預覽、對話切換、MCP 與串流。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.cache_optimizer.optimizer import ContextBudgetError
from core.model_routing.profiles import ModelCatalog
from core.model_routing.requests import InvokeRequest, SwitchRequest
from core.model_routing.router import RoutingError
from core.orchestrator.runtime import AgentRuntime, Session
from mcp_server.client import MCPConnection, as_langchain_tools, connect
from platform_api.auth import KeyStore, Tenant

logger = logging.getLogger(__name__)


class IssueKeyRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=128)


def routing_http_error(exc: RoutingError) -> HTTPException:
    return HTTPException(exc.status_code, {"code": exc.code, "message": str(exc)})


def sse_frame(data: dict[str, Any], event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return prefix + "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"


def create_app(
    *,
    runtime: AgentRuntime | None = None,
    key_store: KeyStore | None = None,
) -> FastAPI:
    service = runtime or AgentRuntime()
    preview = AgentRuntime(catalog=ModelCatalog.demo())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.keys = key_store or KeyStore(
            os.getenv("PLATFORM_KEY_DB") or ".state/keys.sqlite3"
        )
        async with AsyncExitStack() as stack:
            for raw in json.loads(os.getenv("PLATFORM_MCP_SERVERS", "[]")):
                config = MCPConnection.model_validate(raw)
                session = await stack.enter_async_context(connect(config))
                service.external_tools.extend(await as_langchain_tools(session, config.name))
            yield
            service.external_tools.clear()
            service.agents.clear()
            service.tools.clear()

    application = FastAPI(title="OmniAgent / OmniRoute", version="0.2.0", lifespan=lifespan)
    application.state.runtime = service
    application.mount(
        "/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static"
    )

    async def current_tenant(x_api_key: str | None = Header(default=None)) -> Tenant:
        if not x_api_key:
            raise HTTPException(401, "Missing X-API-Key")
        tenant = await asyncio.to_thread(application.state.keys.authenticate, x_api_key)
        if tenant is None:
            raise HTTPException(401, "Invalid API key")
        return tenant

    async def admin(x_admin_key: str | None = Header(default=None)) -> None:
        expected = os.getenv("PLATFORM_ADMIN_KEY")
        if not expected or not x_admin_key or not secrets.compare_digest(expected, x_admin_key):
            raise HTTPException(403, "Administrator key required")

    def resolve(req: InvokeRequest | SwitchRequest, tenant: Tenant) -> tuple[str, Session]:
        try:
            return service.session(tenant.tenant_id, req.agent_id, req.session_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown or unavailable agent") from exc
        except RuntimeError as exc:
            raise HTTPException(503, "Session capacity reached") from exc

    @application.get("/", include_in_schema=False)
    async def console() -> FileResponse:
        return FileResponse(Path(__file__).with_name("console.html"), media_type="text/html")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "platform": "omniagent", "version": "0.2.0"}

    @application.get("/demo/models", tags=["Offline preview"])
    async def demo_models() -> list[dict[str, object]]:
        return preview.catalog.public("preview")

    @application.post("/demo/route", tags=["Offline preview"])
    async def demo_route(req: InvokeRequest) -> dict[str, Any]:
        # 公開預覽只使用獨立示範目錄，不呼叫模型、不建立對話，也不讀取私人目錄。
        if req.agent_id not in preview.configs:
            raise HTTPException(404, "Unknown demo agent")
        try:
            return {
                "preview": True,
                **preview.plan(
                    "preview", req.agent_id, Session(), req.message, **req.routing()
                ).model_dump(),
            }
        except RoutingError as exc:
            raise routing_http_error(exc) from exc

    @application.get("/v1/agents")
    async def agents(tenant: Tenant = Depends(current_tenant)) -> list[dict[str, str]]:
        return [
            {"id": aid, "description": cfg.get("description", "")}
            for aid, cfg in service.configs.items()
            if not cfg.get("tenant_ids") or tenant.tenant_id in cfg["tenant_ids"]
        ]

    @application.get("/v1/models")
    async def models(
        agent_id: str = "default",
        tenant: Tenant = Depends(current_tenant),
    ) -> list[dict[str, object]]:
        try:
            config = service.resolve(tenant.tenant_id, agent_id)
        except KeyError as exc:
            raise HTTPException(404, "Unknown or unavailable agent") from exc
        return service.catalog.public(tenant.tenant_id, config.get("model_ids"))

    @application.post("/v1/route")
    async def route(req: InvokeRequest, tenant: Tenant = Depends(current_tenant)) -> dict[str, Any]:
        sid, state = resolve(req, tenant)
        async with state.lock:
            try:
                decision = service.plan(
                    tenant.tenant_id, req.agent_id, state, req.message, **req.routing()
                )
            except RoutingError as exc:
                raise routing_http_error(exc) from exc
        return {"session_id": sid, "agent_id": req.agent_id, **decision.model_dump()}

    @application.post("/v1/sessions/model")
    async def switch(
        req: SwitchRequest, tenant: Tenant = Depends(current_tenant)
    ) -> dict[str, Any]:
        sid, state = resolve(req, tenant)
        try:
            selection = await service.switch_model(
                tenant.tenant_id,
                req.agent_id,
                state,
                req.model_id,
                preference=req.preference,
                max_cost_tier=req.max_cost_tier,
            )
        except RoutingError as exc:
            raise routing_http_error(exc) from exc
        return {"session_id": sid, "agent_id": req.agent_id, **selection}

    @application.get("/v1/routing/traces")
    async def traces(
        limit: int = Query(default=50, ge=1, le=100),
        tenant: Tenant = Depends(current_tenant),
    ) -> list[dict[str, Any]]:
        return service.route_traces(tenant.tenant_id, limit)

    @application.post("/v1/invoke")
    async def invoke(
        req: InvokeRequest, tenant: Tenant = Depends(current_tenant)
    ) -> dict[str, Any]:
        sid, state = resolve(req, tenant)
        try:
            result = await service.invoke_with_route(
                tenant.tenant_id,
                req.agent_id,
                sid,
                state,
                req.message,
                **req.routing(),
            )
        except RoutingError as exc:
            raise routing_http_error(exc) from exc
        except ContextBudgetError as exc:
            raise HTTPException(413, str(exc)) from exc
        except Exception as exc:
            logger.error("Agent invocation failed (%s)", type(exc).__name__)
            raise HTTPException(503, "Agent unavailable; check server configuration") from exc
        return {
            "output": result.output,
            "agent_id": req.agent_id,
            "session_id": sid,
            "tenant_id": tenant.tenant_id,
            "route": result.route.model_dump(),
        }

    @application.post("/v1/stream")
    async def stream(
        req: InvokeRequest, tenant: Tenant = Depends(current_tenant)
    ) -> StreamingResponse:
        sid, state = resolve(req, tenant)
        try:
            decision = service.plan(
                tenant.tenant_id, req.agent_id, state, req.message, **req.routing()
            )
            await service.prepare(
                service.resolve(tenant.tenant_id, req.agent_id),
                Session(),
                req.message,
                input_budget=decision.input_budget,
            )
        except RoutingError as exc:
            raise routing_http_error(exc) from exc
        except ContextBudgetError as exc:
            raise HTTPException(413, str(exc)) from exc

        async def events() -> AsyncIterator[str]:
            yield sse_frame({"session_id": sid}, "session")
            try:
                async for event in service.stream_events(
                    tenant.tenant_id,
                    req.agent_id,
                    sid,
                    state,
                    req.message,
                    **req.routing(),
                ):
                    if event["type"] == "route":
                        yield sse_frame(event["route"], "route")
                    else:
                        yield sse_frame({"delta": event["delta"]})
            except Exception as exc:
                logger.error("Agent stream failed (%s)", type(exc).__name__)
                yield sse_frame({"error": "Agent unavailable"}, "error")
                return
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post("/v1/keys", dependencies=[Depends(admin)], status_code=201)
    async def issue_key(req: IssueKeyRequest) -> dict[str, str]:
        return await asyncio.to_thread(application.state.keys.issue, req.tenant_id, req.label)

    @application.get("/v1/keys", dependencies=[Depends(admin)])
    async def list_keys() -> list[dict[str, str | bool]]:
        return await asyncio.to_thread(application.state.keys.list_keys)

    @application.delete("/v1/keys/{key_id}", dependencies=[Depends(admin)])
    async def revoke_key(key_id: str) -> dict[str, bool]:
        revoked = await asyncio.to_thread(application.state.keys.revoke, key_id)
        if not revoked:
            raise HTTPException(404, "Unknown managed key")
        return {"revoked": True}

    return application


app = create_app()
