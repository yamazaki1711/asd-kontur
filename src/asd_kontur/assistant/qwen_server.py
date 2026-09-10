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
            if not generation_lock.acquire(blocking=False):
                self.send_error(429)
                return
            try:
                image: Any = None
                if image_bytes is not None:
                    from PIL import Image

                    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                prompt = prompt_utils.apply_chat_template(
                    processor, config, prompt_text, num_images=1 if image is not None else 0
                )
                if self.path == "/vision":
                    response_text = ""
                    for result in mlx_vlm.stream_generate(
                        model,
                        processor,
                        prompt,
                        image=image,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ):
                        response_text = str(result.text)
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
                for result in mlx_vlm.stream_generate(
                    model,
                    processor,
                    prompt,
                    image=image,
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
