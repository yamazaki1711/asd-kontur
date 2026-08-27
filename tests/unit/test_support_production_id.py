from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from asd_kontur.support import (
    DocumentMembershipVersion,
    FieldResolution,
    IdPackageVersion,
    MembershipRevision,
    MembershipState,
    OfficialPdfFormProfile,
    PdfOverlayBinding,
    PdfOverlayRenderer,
    ResolutionState,
    TemplateBackedDocxRenderer,
    VolumeBookVersion,
    evaluate_package_readiness,
    evolve_package_version,
    qualify_official_pdf_form,
    registry_manifest,
)


def _id(value: int) -> UUID:
    return UUID(int=value)


def _member(
    identity: int,
    *,
    role: str,
    ordinal: int,
    state: MembershipState = MembershipState.MISSING,
) -> DocumentMembershipVersion:
    return DocumentMembershipVersion(
        _id(identity),
        1,
        role,
        ordinal,
        1,
        "work_acceptance",
        None if role == "register" else (_id(identity + 100), 1),
        "package_register" if role == "register" else "required_document",
        f"subject:{identity}",
        state,
        (f"evidence:{identity}",),
        ("OUTPUT_BLOCKED",) if state is MembershipState.BLOCKED else (),
    )


def test_package_registry_order_and_readiness_are_deterministic() -> None:
    register = _member(1, role="register", ordinal=1, state=MembershipState.GENERATED_CANDIDATE)
    aosr = _member(2, role="aosr", ordinal=2, state=MembershipState.GENERATED_CANDIDATE)
    scheme = _member(3, role="executive_scheme", ordinal=3, state=MembershipState.BLOCKED)
    book = VolumeBookVersion(_id(20), 1, "ID book", 1, "package", 1, (register, aosr, scheme))
    package = IdPackageVersion(
        _id(10),
        1,
        (_id(30), 1),
        (_id(40), 1),
        _id(50),
        "support.executive-document-package",
        (book,),
    )

    manifest = registry_manifest(package, book)
    readiness = evaluate_package_readiness(package)

    assert [item["ordinal"] for item in manifest["documents"]] == [2, 3]
    assert all(item["role"] != "register" for item in manifest["documents"])
    assert readiness.required == 2
    assert readiness.generated_candidates == 1
    assert readiness.blocked == 1
    assert readiness.status == "incomplete"
    assert evaluate_package_readiness(package).fingerprint == readiness.fingerprint


def test_package_evolution_regenerates_register_without_mutating_history() -> None:
    register = _member(1, role="register", ordinal=1)
    aosr = _member(2, role="aosr", ordinal=2, state=MembershipState.GENERATED_CANDIDATE)
    quality = _member(3, role="quality", ordinal=3)
    original = IdPackageVersion(
        _id(10),
        1,
        (_id(30), 1),
        (_id(40), 1),
        _id(50),
        "support.executive-document-package",
        (VolumeBookVersion(_id(20), 1, "ID book", 1, "package", 1, (register, aosr, quality)),),
    )

    finalized = evolve_package_version(
        original,
        revisions=(
            MembershipRevision(
                aosr.membership_id,
                "finalized_document",
                "finalized:1:v1",
                MembershipState.FINALIZED,
                evidence_refs=("sha256:" + "a" * 64,),
                blocker_codes=(),
            ),
        ),
    )
    reordered = evolve_package_version(
        finalized,
        body_order=(quality.membership_id, aosr.membership_id),
    )
    removed = evolve_package_version(reordered, removed_membership_ids=(quality.membership_id,))

    assert original.version == 1
    assert original.books[0].memberships[1].subject_kind == "required_document"
    assert finalized.version == 2
    assert finalized.books[0].memberships[0].subject_ref.endswith(":v2")
    assert finalized.books[0].memberships[1].state is MembershipState.FINALIZED
    assert [
        item["role"] for item in registry_manifest(reordered, reordered.books[0])["documents"]
    ] == [
        "quality",
        "aosr",
    ]
    assert [item["role"] for item in registry_manifest(removed, removed.books[0])["documents"]] == [
        "aosr"
    ]
    assert len({item.ordinal for item in removed.books[0].memberships}) == len(
        removed.books[0].memberships
    )


def test_register_ordinal_and_duplicate_memberships_fail_closed() -> None:
    with pytest.raises(ValueError, match="ordinal 1"):
        _member(1, role="register", ordinal=2)
    with pytest.raises(ValueError, match="reserved"):
        _member(2, role="aosr", ordinal=1)


def test_template_renderer_is_fresh_deterministic_and_evidence_bound() -> None:
    template = _template_docx(b"Object: {{object_name}}; volume: {{work_volume}}")
    digest = "sha256:" + hashlib.sha256(template).hexdigest()
    fields = (
        FieldResolution(
            "object_name",
            ResolutionState.CONFIRMED,
            "Synthetic object",
            "Synthetic object",
            _id(100),
            1,
            (_id(101),),
            (_id(102),),
        ),
        FieldResolution(
            "work_volume",
            ResolutionState.CONFIRMED,
            "12.350 m3",
            "12.350 м³",
            _id(103),
            1,
            (_id(104),),
            (_id(105),),
        ),
    )
    renderer = TemplateBackedDocxRenderer()

    first = renderer.render(
        template_bytes=template,
        template_digest=digest,
        fields=fields,
        semantic_input={"run": "one"},
    )
    second = renderer.render(
        template_bytes=template,
        template_digest=digest,
        fields=fields,
        semantic_input={"run": "one"},
    )

    assert first.package_bytes == second.package_bytes
    assert first.bytes_digest == second.bytes_digest
    with zipfile.ZipFile(io.BytesIO(first.package_bytes)) as package:
        document = package.read("word/document.xml")
    assert b"Synthetic object" in document
    assert "12.350 м³".encode() in document
    assert b"{{" not in document


def test_template_renderer_never_fills_missing_material_field() -> None:
    template = _template_docx(b"Object: {{object_name}}")
    digest = "sha256:" + hashlib.sha256(template).hexdigest()
    missing = FieldResolution(
        "object_name",
        ResolutionState.MISSING,
        None,
        None,
        None,
        None,
        (),
        (),
    )
    with pytest.raises(ValueError, match="generation_material_fields_unresolved"):
        TemplateBackedDocxRenderer().render(
            template_bytes=template,
            template_digest=digest,
            fields=(missing,),
            semantic_input={},
        )


def test_pdf_overlay_qualification_and_render_are_deterministic() -> None:
    source = _source_pdf()
    source_digest = "sha256:" + hashlib.sha256(source).hexdigest()
    binding = PdfOverlayBinding("object_name", 1, 72, 650, 450, 40, 9, 11)
    profile = OfficialPdfFormProfile(
        "test.binding@1.0.0",
        source_digest,
        "source-version:test@1",
        "normative-edition:test@1",
        "https://example.test/official.pdf",
        (1, 2),
        ("Appendix 3", "Hidden works act"),
        (binding,),
        "support.pdf-overlay-renderer@1.0.0",
        "support.pdf-print-validator@1.0.0",
    )
    template, qualification = qualify_official_pdf_form(source_bytes=source, profile=profile)
    font = next(
        path
        for path in (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        )
        if path.is_file()
    ).read_bytes()
    field = FieldResolution(
        "object_name",
        ResolutionState.CONFIRMED,
        "Evidence-bound construction object",
        "Evidence-bound construction object",
        _id(100),
        1,
        (_id(101),),
        (_id(102),),
    )
    renderer = PdfOverlayRenderer()
    kwargs = {
        "template_bytes": template,
        "template_digest": qualification.template_digest,
        "fields": (field,),
        "bindings": (binding,),
        "font_bytes": font,
        "font_digest": "sha256:" + hashlib.sha256(font).hexdigest(),
        "renderer_profile_version": profile.renderer_profile_version,
        "validator_profile_version": profile.validator_profile_version,
        "semantic_input": {"run": "same"},
    }
    first, first_receipt = renderer.render(**kwargs)
    second, second_receipt = renderer.render(**kwargs)

    assert qualification.result == "qualified"
    assert first.package_bytes == second.package_bytes
    assert first_receipt.result == "print_ready"
    assert first_receipt.fingerprint == second_receipt.fingerprint
    assert (
        "Evidence-bound construction object"
        in __import__("pypdf").PdfReader(io.BytesIO(first.package_bytes)).pages[0].extract_text()
    )


def _template_docx(document_text: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        package.writestr(
            "word/document.xml",
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body><w:p><w:r><w:t>"
            + document_text
            + b"</w:t></w:r></w:p></w:body></w:document>",
        )
    return buffer.getvalue()


def _source_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    writer = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    writer.drawString(72, 780, "Appendix 3")
    writer.drawString(72, 750, "Hidden works act")
    writer.showPage()
    writer.drawString(72, 780, "Continuation")
    writer.showPage()
    writer.save()
    return buffer.getvalue()
