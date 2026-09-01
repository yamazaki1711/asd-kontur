"""Loopback-only streaming Qwen3.8 MLX process.

This module intentionally uses only the Python standard library plus mlx-vlm so
it can run in the pinned MLX virtual environment without importing the
application or PostgreSQL clients.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8790, type=int)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("qwen_server_must_bind_loopback")
    import mlx_vlm  # type: ignore[import-not-found]
    from mlx_vlm import prompt_utils

    model, processor = mlx_vlm.load(str(args.model))
    config = model.config
    generation_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "ASDKonturQwen/1.0"

        def log_message(self, format: str, *values: Any) -> None:
            del format, values

        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            payload = json.dumps(
                {"status": "ready", "model": "Qwen3.8-27B"}, ensure_ascii=False
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            if self.path != "/generate":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 2_000_000:
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
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            if not generation_lock.acquire(blocking=False):
                self.send_error(429)
                return
            try:
                prompt = prompt_utils.apply_chat_template(
                    processor, config, prompt_text, num_images=0
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write({"event": "started", "model": "Qwen3.8-27B"})
                prior = ""
                for result in mlx_vlm.stream_generate(
                    model,
                    processor,
                    prompt,
                    image=None,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    current = str(result.text)
                    delta = current[len(prior) :] if current.startswith(prior) else current
                    prior = current
                    if delta:
                        self._write({"event": "delta", "text": delta})
                self._write({"event": "completed"})
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                generation_lock.release()

        def _write(self, payload: dict[str, Any]) -> None:
            self.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
