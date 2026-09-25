#!/usr/bin/env python3
"""Compare local multilingual embedding candidates on a pinned NTD rubric."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
    return "sha256:" + digest.hexdigest()


def reciprocal_rank(order: list[int], expected: set[int]) -> float:
    for rank, index in enumerate(order, 1):
        if index in expected:
            return 1.0 / rank
    return 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--model", required=True, action="append")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_bytes())
    passages = list(cases["passages"])
    results = []
    for model_value in args.model:
        model_path = Path(model_value).resolve(strict=True)
        model = SentenceTransformer(str(model_path), device="mps")
        passage_vectors = model.encode(passages, normalize_embeddings=True, convert_to_numpy=True)
        query_vectors = model.encode(
            [item["query"] for item in cases["queries"]],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        scores = np.matmul(query_vectors, passage_vectors.T)
        rr = []
        top1 = 0
        for index, item in enumerate(cases["queries"]):
            order = [int(value) for value in np.argsort(-scores[index])]
            expected = set(item["relevant_passage_indexes"])
            rr.append(reciprocal_rank(order, expected))
            top1 += bool(order and order[0] in expected)
        results.append(
            {
                "model_path": str(model_path),
                "model_digest": tree_digest(model_path),
                "dimension": int(model.get_sentence_embedding_dimension()),
                "queries": len(cases["queries"]),
                "mrr": sum(rr) / len(rr),
                "recall_at_1": top1 / len(rr),
            }
        )
    results.sort(key=lambda item: (-item["mrr"], -item["recall_at_1"], item["model_path"]))
    payload = {
        "schema_version": "ntd-embedding-qualification@1.0.0",
        "cases_digest": "sha256:" + hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "results": results,
        "selected": results[0],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
