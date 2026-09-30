"""Loopback-only streaming Qwen3.8 MLX process.

This module intentionally uses only the Python standard library plus mlx-vlm so
it can run in the pinned MLX virtual environment without importing the
application or PostgreSQL clients.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _collect_generated_text(results: Iterable[Any]) -> str:
    """Join MLX-VLM streaming segments without treating a delta as a full response."""

    return "".join(str(result.text) for result in results)


class QwenRuntimeState:
    """Thread-safe lightweight state independent of the heavy generation loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "QWEN_MODEL_LOADING"
        self._status_changed_at = datetime.now(UTC).isoformat()
        self._generation_started_at: str | None = None
        self._completed_requests = 0
        self._last_error: str | None = None
        self._runtime: tuple[Any, Any, Any] | None = None

    def model_ready(self, model: Any, processor: Any, config: Any) -> None:
        with self._lock:
            self._runtime = (model, processor, config)
            self._set_status("QWEN_READY_IDLE")

    def model_error(self, error: BaseException) -> None:
        with self._lock:
            self._last_error = type(error).__name__
            self._set_status("QWEN_ERROR")

    def generation_started(self) -> None:
        with self._lock:
            self._generation_started_at = datetime.now(UTC).isoformat()
            self._set_status("QWEN_GENERATING")

    def generation_finished(self, error: BaseException | None = None) -> None:
        with self._lock:
            self._completed_requests += 1
            self._generation_started_at = None
            self._last_error = type(error).__name__ if error is not None else None
            self._set_status("QWEN_READY_IDLE")

    def runtime(self) -> tuple[Any, Any, Any] | None:
        with self._lock:
            return self._runtime

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "model": "Qwen3.8-27B",
                "status_changed_at": self._status_changed_at,
                "generation_started_at": self._generation_started_at,
                "completed_requests": self._completed_requests,
                "last_error": self._last_error,
            }

    def _set_status(self, status: str) -> None:
        self._status = status
        self._status_changed_at = datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8790, type=int)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("qwen_server_must_bind_loopback")
    state = QwenRuntimeState()
    generation_lock = threading.Lock()

    def load_model() -> None:
        try:
            import mlx_vlm  # type: ignore[import-not-found]

            model, processor = mlx_vlm.load(str(args.model))
            state.model_ready(model, processor, model.config)
        except BaseException as exc:  # the status endpoint must survive a fatal loader error
            state.model_error(exc)

    threading.Thread(target=load_model, name="qwen-model-loader", daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "ASDKonturQwen/1.0"

        def log_message(self, format: str, *values: Any) -> None:
            del format, values

        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            payload = json.dumps(state.snapshot(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            if self.path not in {"/generate", "/vision"}:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            ceiling = 16_000_000 if self.path == "/vision" else 2_000_000
            if length < 2 or length > ceiling:
                self.send_error(413)
                return
            try:
                request = json.loads(self.rfile.read(length))
                prompt_text = str(request["prompt"])
                generation_ceiling = (
                    6000 if prompt_text.startswith("Role: qwen3.8-27b-developer-worker@") else 1800
                )
                max_tokens = min(generation_ceiling, max(64, int(request.get("max_tokens", 1200))))
                temperature = float(request.get("temperature", 0.2))
                if not 0.0 <= temperature <= 0.7:
                    raise ValueError("temperature outside qualified range")
                image_bytes: bytes | None = None
                if self.path == "/vision":
                    encoded = request["image_base64"]
                    if not isinstance(encoded, str):
                        raise ValueError("image encoding invalid")
                    image_bytes = base64.b64decode(encoded, validate=True)
                    if not image_bytes or len(image_bytes) > 12 * 1024 * 1024:
                        raise ValueError("image size invalid")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            runtime = state.runtime()
            if runtime is None:
                self.send_error(503)
                return
            if not generation_lock.acquire(blocking=False):
                self.send_error(429)
                return
            generation_error: BaseException | None = None
            try:
                model, processor, config = runtime
                import mlx_vlm
                from mlx_vlm import prompt_utils

                state.generation_started()
                image: Any = None
                if image_bytes is not None:
                    from PIL import Image

                    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                prompt = prompt_utils.apply_chat_template(
                    processor,
                    config,
                    prompt_text,
                    num_images=1 if image is not None else 0,
                    enable_thinking=False,
                )
                if self.path == "/vision":
                    response_text = _collect_generated_text(
                        mlx_vlm.stream_generate(
                            model,
                            processor,
                            prompt,
                            image=image,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    )
                    payload = json.dumps(
                        {"model": "Qwen3.8-27B", "text": response_text}, ensure_ascii=False
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write({"event": "started", "model": "Qwen3.8-27B"})
                prior = ""
                generation_events = 0
                for result in mlx_vlm.stream_generate(
                    model,
                    processor,
                    prompt,
                    image=image,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    generation_events += 1
                    current = str(result.text)
                    delta = current[len(prior) :] if current.startswith(prior) else current
                    prior = current
                    if delta:
                        self._write({"event": "delta", "text": delta})
                self._write(
                    {
                        "event": "completed",
                        "generation_events": generation_events,
                        "max_tokens": max_tokens,
                        "limit_reached": generation_events >= max_tokens,
                    }
                )
            except (BrokenPipeError, ConnectionResetError):
                pass
            except BaseException as exc:
                generation_error = exc
                raise
            finally:
                state.generation_finished(generation_error)
                generation_lock.release()

        def _write(self, payload: dict[str, Any]) -> None:
            self.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
