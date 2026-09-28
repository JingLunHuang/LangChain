"""OmniAgent CLI：模型目錄、路由預覽與 Agent 執行。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from pydantic import ValidationError

from core.model_routing.profiles import ModelCatalog
from core.model_routing.requests import InvokeRequest
from core.model_routing.router import RoutingError
from core.orchestrator.runtime import AgentRuntime, Session


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="omniagent", description="OmniRoute 任務與模型路由")
    subcommands = command.add_subparsers(dest="command", required=True)
    subcommands.add_parser("models", help="列出模型能力與設定狀態")
    for name in ("route", "run"):
        operation = subcommands.add_parser(
            name, help="預覽路由" if name == "route" else "執行 Agent"
        )
        operation.add_argument("message")
        operation.add_argument("--model", default="auto", help="模型 ID；預設依任務自動選擇")
        operation.add_argument("--agent", default="chat", choices=["default", "chat"])
        operation.add_argument(
            "--preference",
            default="balanced",
            choices=["balanced", "quality", "economy", "latency"],
        )
        operation.add_argument(
            "--task", choices=["general", "coding", "reasoning", "writing", "knowledge"]
        )
        operation.add_argument("--max-cost-tier", type=int, choices=[1, 2, 3], default=3)
    return command


async def execute(args: argparse.Namespace) -> Any:
    request = InvokeRequest(
        message=args.message,
        agent_id=args.agent,
        model_id=args.model,
        preference=args.preference,
        task=args.task,
        max_cost_tier=args.max_cost_tier,
    )
    runtime = AgentRuntime()
    if args.command == "route":
        return runtime.plan(
            "cli-local", request.agent_id, Session(), request.message, **request.routing()
        ).model_dump()
    sid, state = runtime.session("cli-local", request.agent_id, request.session_id)
    result = await runtime.invoke_with_route(
        "cli-local", request.agent_id, sid, state, request.message, **request.routing()
    )
    return {"output": result.output, "session_id": sid, "route": result.route.model_dump()}


def main() -> int:
    args = parser().parse_args()
    try:
        result = (
            ModelCatalog.from_environment().public("cli-local")
            if args.command == "models"
            else asyncio.run(execute(args))
        )
    except ValidationError:
        print(json.dumps({"error": "Invalid request", "code": "invalid_request"}))
        return 1
    except RoutingError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"error": "Check platform model settings", "type": type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
