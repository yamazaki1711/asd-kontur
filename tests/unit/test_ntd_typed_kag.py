from uuid import UUID

import pytest

from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.retrieval_qualification import (
    QualificationCorpusEntry,
    QualificationDocument,
    QualificationUnit,
)
from asd_kontur.ntd.typed_kag import build_qualification_kag


def _document(designation: str, digest: str, text: str) -> QualificationDocument:
    unit = QualificationUnit(
        deterministic_uuid(f"test-ntd-unit:{digest}"),
        digest,
        1,
        "clause",
        "7.1",
        None,
        "7.1 Требования",
        "7.1",
        (3,),
        (3,),
        text,
        text.casefold(),
    )
    return QualificationDocument(
        QualificationCorpusEntry(
            designation,
            f"Документ {designation}",
            digest,
            "official",
            5,
            None,
            (),
        ),
        (unit,),
        ("", "", text, "", ""),
    )


def test_typed_kag_materializes_only_explicit_structure_and_exact_reference() -> None:
    sp70 = _document("СП 70.13330.2012", "sha256:" + "7" * 64, "Бетонные работы")
    sp543 = _document(
        "СП 543.1325800.2024",
        "sha256:" + "5" * 64,
        "Ссылка на СП 70.13330.2012",
    )

    graph = build_qualification_kag((sp70, sp543))

    assert sum(edge.relation == "contains" for edge in graph.edges) == 2
    assert sum(edge.relation == "references" for edge in graph.edges) == 1
    assert not graph.candidates
    assert all(
        edge.authority_method in {"explicit_structure", "exact_reference"} for edge in graph.edges
    )
    assert graph.fingerprint == build_qualification_kag((sp70, sp543)).fingerprint


def test_typed_kag_path_expansion_is_bounded() -> None:
    document = _document("СП 70.13330.2012", "sha256:" + "7" * 64, "Бетонные работы")
    graph = build_qualification_kag((document,))
    root = next(node for node in graph.nodes if node.kind == "normative_document")

    expanded = graph.expand((root.node_id,), max_depth=1, max_nodes=2)

    assert len(expanded) == 2
    assert all(isinstance(node_id, UUID) for node_id in expanded)
    with pytest.raises(ValueError, match="ntd_kag_expansion_bound_invalid"):
        graph.expand((root.node_id,), max_depth=5)
