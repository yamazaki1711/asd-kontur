"""Loopback-only persistent embedding worker for canonical NTD chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    return "sha256:" + digest.hexdigest()


class EmbeddingRuntime:
    def __init__(self, *, model_path: Path, profile_path: Path) -> None:
        import importlib
        import json

        embedding_loader = importlib.import_module("mlx_vlm.embedding_loader")
        pooling = importlib.import_module("mlx_vlm.models.pooling")
        utils = importlib.import_module("mlx_vlm.utils")

        load_embedding_model = embedding_loader.load_embedding_model
        read_pooling_config = pooling.read_pooling_config
        load_processor = utils.load_processor
        profile = json.loads(profile_path.read_bytes())
        if profile["model_digest"] != _tree_digest(model_path):
            raise ValueError("embedding_model_digest_mismatch")

        query_prefix = profile.get("query_prefix")
        if not isinstance(query_prefix, str) or not query_prefix:
            raise ValueError("embedding_profile_query_prefix_missing")

        if profile.get("normalization") != "l2":
            raise ValueError("embedding_profile_normalization_unsupported")

        self.profile = profile
        self.query_prefix = query_prefix

        self.model = load_embedding_model(model_path)
        self.processor = load_processor(model_path, add_detokenizer=False)
        self.model.pooling_config = read_pooling_config(model_path)

        dimension = int(self.model.config.hidden_size)
        if dimension != int(profile["dimension"]):
            raise ValueError("embedding_model_dimension_mismatch")

    def encode(self, texts: list[str]) -> list[list[float]]:
        import importlib
        import math

        mx = importlib.import_module("mlx.core")

        if (
            not texts
            or len(texts) > 128
            or any(not value.strip() or len(value) > 16000 for value in texts)
        ):
            raise ValueError("embedding_request_invalid")

        tokenizer = getattr(self.processor, "tokenizer", self.processor)
        max_length = min(getattr(tokenizer, "model_max_length", 512) or 512, 8192)
        prefixed_texts = [self.query_prefix + text for text in texts]
        encoded = tokenizer(
            prefixed_texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="np",
        )

        input_ids = mx.array(encoded["input_ids"])
        attention_mask = mx.array(encoded["attention_mask"])

        out = self.model(input_ids=input_ids, attention_mask=attention_mask)
        if not hasattr(out, "text_embeds"):
            raise ValueError("embedding_model_output_missing")

        embeds = out.text_embeds
        mx.eval(embeds)
        if embeds.shape[0] != len(texts):
            raise ValueError("embedding_request_invalid")

        expected_dim = int(self.profile["dimension"])
        result: list[list[float]] = []
        for index in range(len(texts)):
            vector = embeds[index]
            if vector.shape[0] != expected_dim:
                raise ValueError("embedding_request_invalid")
            row: list[float] = []
            for component_index in range(expected_dim):
                val = float(vector[component_index])
                if not math.isfinite(val):
                    raise ValueError("embedding_request_invalid")
                row.append(val)
            result.append(row)

        return result


def serve(*, model_path: Path, profile_path: Path, host: str, port: int) -> None:
    if host != "127.0.0.1":
        raise ValueError("embedding_worker_must_be_loopback")
    runtime = EmbeddingRuntime(model_path=model_path, profile_path=profile_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health/ready":
                self.send_error(404)
                return
            self._json(200, {"status": "ready", "profile_key": runtime.profile["profile_key"]})

        def do_POST(self) -> None:
            if self.path != "/v1/embeddings":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 2 or length > 2 * 1024 * 1024:
                    raise ValueError("embedding_payload_size_invalid")
                payload: dict[str, Any] = json.loads(self.rfile.read(length))
                if payload.get("profile") != runtime.profile["profile_key"]:
                    raise ValueError("embedding_profile_not_allowed")
                texts = payload.get("texts")
                if not isinstance(texts, list) or not all(
                    isinstance(value, str) for value in texts
                ):
                    raise ValueError("embedding_texts_invalid")
                vectors = runtime.encode(texts)
                self._json(
                    200,
                    {
                        "profile_key": runtime.profile["profile_key"],
                        "profile_version": runtime.profile["profile_version"],
                        "dimension": runtime.profile["dimension"],
                        "embeddings": vectors,
                    },
                )
            except (ValueError, json.JSONDecodeError) as error:
                self._json(422, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8791, type=int)
    args = parser.parse_args()
    serve(
        model_path=args.model.resolve(strict=True),
        profile_path=args.profile.resolve(strict=True),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
