"""Run bounded chat-runtime regression cases against the gateway entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

from fastapi.testclient import TestClient

from apps.api_gateway.main import create_app
from shared.chat_runtime_eval import (
    evaluate_chat_response,
    load_eval_cases,
    summarize_eval_results,
)


def main(argv: list[str] | None = None) -> int:
    """Run a set of chat-runtime evaluation cases and print a JSON summary."""
    parser = argparse.ArgumentParser(description="Evaluate bounded /chat self-scheduling behavior.")
    parser.add_argument(
        "--cases",
        default="tests/data/chat_runtime_eval_cases.json",
        help="Path to the JSON evaluation case file.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Optional external gateway base URL. When omitted, runs in-process via FastAPI TestClient.",
    )
    args = parser.parse_args(argv)

    cases = load_eval_cases(args.cases)
    responses = [
        _post_chat(
            base_url=args.base_url,
            payload={
                "request_id": f"eval-{index + 1:03d}",
                "user_id": case.user_id,
                "message": case.message,
                "mode": case.mode,
                "extra_params": {},
            },
        )
        for index, case in enumerate(cases)
    ]
    results = [
        evaluate_chat_response(case, response_payload)
        for case, response_payload in zip(cases, responses, strict=True)
    ]
    summary = summarize_eval_results(results)
    print(json.dumps(summary.model_dump(), ensure_ascii=False, indent=2))
    return 0 if summary.failed == 0 else 1


def _post_chat(*, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if base_url:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib_request.Request(
            url=f"{base_url.rstrip('/')}/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/chat", json=payload)
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    raise SystemExit(main())
