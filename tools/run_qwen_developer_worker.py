#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from asd_kontur.assistant.developer_worker import (
    PROFILE,
    DeveloperProposal,
    DeveloperRequest,
    parse_proposal,
    validate_generation_tokens,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8790/generate")
    parser.add_argument("--max-tokens", default=1800, type=int)
    return parser.parse_args()


def _load_request(path: Path) -> DeveloperRequest:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("invalid_request_type")
    data = cast(dict[str, object], loaded)
    required = {
        "task_id",
        "objective",
        "allowed_files",
        "readonly_files",
        "invariants",
        "acceptance",
        "context_files",
    }
    if set(data) != required:
        raise ValueError("invalid_request_keys")
    context_raw = data["context_files"]
    if not isinstance(context_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in context_raw.items()
    ):
        raise ValueError("invalid_context_files")
    return DeveloperRequest(
        task_id=_string(data["task_id"], "task_id"),
        objective=_string(data["objective"], "objective"),
        allowed_files=_string_list(data["allowed_files"], "allowed_files"),
        readonly_files=_string_list(data["readonly_files"], "readonly_files"),
        invariants=_string_list(data["invariants"], "invariants"),
        acceptance=_string_list(data["acceptance"], "acceptance"),
        context_files=cast(dict[str, str], context_raw),
    )


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid_{name}")
    return value


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid_{name}")
    return tuple(value)


def _validate_endpoint(endpoint: str) -> None:
    parsed = urllib.parse.urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != 8790
        or parsed.path != "/generate"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("developer_worker_endpoint_not_loopback")


def _invoke(request: DeveloperRequest, endpoint: str, max_tokens: int) -> tuple[str, str]:
    validate_generation_tokens(max_tokens)
    payload = json.dumps(
        {"prompt": request.prompt(), "max_tokens": max_tokens, "temperature": 0.1},
        ensure_ascii=False,
    ).encode()
    http_request = urllib.request.Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(http_request, timeout=900) as response:
        if not response.headers.get("Content-Type", "").startswith("application/x-ndjson"):
            raise ValueError("developer_worker_content_type_invalid")
        model = ""
        fragments: list[str] = []
        state = "initial"
        for raw_line in response:
            if not raw_line.strip():
                continue
            event_raw: object = json.loads(raw_line)
            if not isinstance(event_raw, dict):
                raise ValueError("developer_worker_event_invalid")
            event = cast(dict[str, object], event_raw)
            event_name = event.get("event")
            if event_name == "started" and state == "initial":
                if event.get("model") != "Qwen3.8-27B":
                    raise ValueError("developer_worker_model_invalid")
                model, state = "Qwen3.8-27B", "streaming"
            elif event_name == "delta" and state == "streaming":
                text = event.get("text")
                if not isinstance(text, str):
                    raise ValueError("developer_worker_delta_invalid")
                fragments.append(text)
            elif event_name == "completed" and state == "streaming":
                state = "completed"
            else:
                raise ValueError("developer_worker_event_order_invalid")
        if state != "completed" or not fragments:
            raise ValueError("developer_worker_stream_incomplete")
        return "".join(fragments), model


def _proposal_payload(proposal: DeveloperProposal) -> dict[str, object]:
    return {
        "plan": list(proposal.plan),
        "unified_diff": proposal.unified_diff,
        "tests": list(proposal.tests),
        "assumptions": list(proposal.assumptions),
        "terminal_outcome": proposal.terminal_outcome,
    }


def _write_outputs(response: Path, receipt: Path, payloads: tuple[object, object]) -> None:
    invalid_path = (
        response.exists()
        or receipt.exists()
        or not response.parent.is_dir()
        or not receipt.parent.is_dir()
    )
    if invalid_path:
        raise ValueError("developer_worker_output_path_invalid")
    temporary: list[Path] = []
    try:
        for target, payload in zip((response, receipt), payloads, strict=True):
            descriptor, raw_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            path = Path(raw_path)
            temporary.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        os.replace(temporary[0], response)
        os.replace(temporary[1], receipt)
        temporary.clear()
    except Exception:
        response.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


def main() -> int:
    arguments = _args()
    try:
        _validate_endpoint(arguments.endpoint)
        request = _load_request(arguments.request)
        raw, model = _invoke(request, arguments.endpoint, arguments.max_tokens)
        proposal = parse_proposal(raw, request.allowed_files)
        response = _proposal_payload(proposal)
        receipt = {
            "profile": PROFILE,
            "model": model,
            "request_digest": request.digest,
            "response_digest": proposal.digest,
            "terminal_outcome": proposal.terminal_outcome,
            "created_at": datetime.now(UTC).isoformat(),
            "endpoint": arguments.endpoint,
        }
        _write_outputs(arguments.response, arguments.receipt, (response, receipt))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"developer_worker_failed:{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
