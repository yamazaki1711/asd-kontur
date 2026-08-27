# ruff: noqa: E501
"""Publication port for qualified official PDF form templates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.application_spine.object_store import WorkspaceObjectStore
from asd_kontur.domain import deterministic_uuid

from .template_qualification import (
    OfficialPdfFormProfile,
    qualify_official_pdf_form,
)


@dataclass(frozen=True, slots=True)
class QualifiedTemplatePublication:
    template_source_id: UUID
    template_id: UUID
    template_version: str
    field_schema_id: UUID
    field_schema_version: str
    source_object_key: str
    template_object_key: str
    font_object_key: str
    source_digest: str
    template_digest: str
    font_digest: str
    qualification_receipt_digest: str


class OfficialTemplatePublisher:
    """Persist a qualified template without weakening its source authority."""

    def __init__(self, engine: Engine, object_store: WorkspaceObjectStore) -> None:
        self._engine = engine
        self._object_store = object_store

    def publish_pdf_overlay(
        self,
        *,
        stable_key: str,
        template_version: str,
        field_schema_version: str,
        source_bytes: bytes,
        font_bytes: bytes,
        font_media_type: str,
        profile: OfficialPdfFormProfile,
        required_document_type_id: UUID | None = None,
        required_document_type_version: str | None = None,
    ) -> QualifiedTemplatePublication:
        if (required_document_type_id is None) != (required_document_type_version is None):
            raise ValueError("template mapping requires both document type identity and version")
        template_bytes, receipt = qualify_official_pdf_form(
            source_bytes=source_bytes, profile=profile
        )
        source_key = f"platform/template-sources/{receipt.source_digest[7:]}"
        template_key = f"platform/templates/{receipt.template_digest[7:]}.pdf"
        font_digest = "sha256:" + hashlib.sha256(font_bytes).hexdigest()
        font_key = f"platform/template-assets/fonts/{font_digest[7:]}"
        assert self._object_store.put_derived(object_key=source_key, content=source_bytes)[0] == (
            receipt.source_digest
        )
        assert (
            self._object_store.put_derived(object_key=template_key, content=template_bytes)[0]
            == receipt.template_digest
        )
        assert self._object_store.put_derived(object_key=font_key, content=font_bytes)[0] == (
            font_digest
        )
        source_id = deterministic_uuid(f"template-source:{stable_key}")
        template_id = deterministic_uuid(f"template:{stable_key}:{template_version}")
        schema_id = deterministic_uuid(f"field-schema:{stable_key}:{field_schema_version}")
        field_manifest_digest = semantic_digest(profile.bindings)
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.template_sources "
                    "(template_source_id,stable_key,format,source_kind,source_digest,provenance_ref,"
                    "rights_status,authority_status,created_at) VALUES "
                    "(:source,:key,'PDF_OVERLAY','official_candidate',:digest,:provenance,'verified',"
                    "'verified',:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "source": source_id,
                    "key": stable_key,
                    "digest": receipt.source_digest,
                    "provenance": json.dumps(
                        {
                            "official_url": receipt.official_url,
                            "source_version_ref": receipt.source_version_ref,
                            "normative_edition_ref": receipt.normative_edition_ref,
                            "source_object_key": source_key,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.field_schema_versions "
                    "(field_schema_id,version,schema_key,field_manifest_digest,status,created_at) "
                    "VALUES (:schema,:version,:key,:digest,'active',:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "schema": schema_id,
                    "version": field_schema_version,
                    "key": f"{stable_key}.fields",
                    "digest": field_manifest_digest,
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.template_versions "
                    "(template_id,version,template_source_id,format,field_schema_id,"
                    "field_schema_version,binding_profile_version,renderer_profile_version,"
                    "validator_profile_version,qualification_state,assurance_class,official_status,"
                    "template_digest,created_at) VALUES "
                    "(:template,:version,:source,'PDF_OVERLAY',:schema,:schema_version,:binding,"
                    ":renderer,:validator,'active','production','verified',:digest,:now) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "template": template_id,
                    "version": template_version,
                    "source": source_id,
                    "schema": schema_id,
                    "schema_version": field_schema_version,
                    "binding": profile.profile_version,
                    "renderer": profile.renderer_profile_version,
                    "validator": profile.validator_profile_version,
                    "digest": receipt.template_digest,
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.template_artifacts "
                    "(template_id,template_version,artifact_version,object_key,media_type,byte_length,"
                    "content_digest,source_provenance,validation_status,validation_receipt_digest,created_at) "
                    "VALUES (:template,:version,1,:object,'application/pdf',:length,:digest,"
                    "CAST(:provenance AS jsonb),'qualified',:receipt,:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "template": template_id,
                    "version": template_version,
                    "object": template_key,
                    "length": len(template_bytes),
                    "digest": receipt.template_digest,
                    "provenance": json.dumps(
                        {
                            "official_source_digest": receipt.source_digest,
                            "official_url": receipt.official_url,
                            "selected_pages": receipt.selected_pages,
                            "qualification_receipt": receipt.fingerprint,
                        },
                        sort_keys=True,
                    ),
                    "receipt": receipt.fingerprint,
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.template_qualification_receipts "
                    "(template_id,template_version,qualification_version,source_version_ref,"
                    "normative_edition_ref,official_url,official_source_digest,selected_pages,"
                    "profile_version,renderer_profile_version,validator_profile_version,check_codes,"
                    "blocker_codes,result,receipt_digest,qualified_at) VALUES "
                    "(:template,:version,1,:source_version,:edition,:url,:source_digest,:pages,"
                    ":profile,:renderer,:validator,:checks,ARRAY[]::text[],'qualified',:receipt,:now) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "template": template_id,
                    "version": template_version,
                    "source_version": receipt.source_version_ref,
                    "edition": receipt.normative_edition_ref,
                    "url": receipt.official_url,
                    "source_digest": receipt.source_digest,
                    "pages": list(receipt.selected_pages),
                    "profile": profile.profile_version,
                    "renderer": profile.renderer_profile_version,
                    "validator": profile.validator_profile_version,
                    "checks": list(receipt.check_codes),
                    "receipt": receipt.fingerprint,
                    "now": now,
                },
            )
            for order, binding in enumerate(profile.bindings, start=1):
                definition_digest = semantic_digest(
                    {
                        "field_key": binding.field_key,
                        "material": binding.material,
                        "required": binding.required,
                        "repeatable": False,
                        "value_type": "text",
                    }
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO platform.template_field_definitions "
                        "(field_schema_id,field_schema_version,field_key,value_type,material,required,"
                        "repeatable,binding_token,display_order,definition_digest) VALUES "
                        "(:schema,:version,:field,'text',:material,:required,false,:token,:order,:digest) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "schema": schema_id,
                        "version": field_schema_version,
                        "field": binding.field_key,
                        "material": binding.material,
                        "required": binding.required,
                        "token": f"pdf-overlay:{binding.field_key}",
                        "order": order,
                        "digest": definition_digest,
                    },
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO platform.template_field_binding_versions "
                        "(template_id,template_version,field_key,binding_version,page_index,region,"
                        "typography,binding_digest) VALUES "
                        "(:template,:version,:field,:binding,:page,:region,CAST(:typography AS jsonb),"
                        ":digest) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "template": template_id,
                        "version": template_version,
                        "field": binding.field_key,
                        "binding": profile.profile_version,
                        "page": binding.page_index,
                        "region": [binding.x, binding.y, binding.width, binding.height],
                        "typography": json.dumps(
                            {
                                "font_size": binding.font_size,
                                "line_height": binding.line_height,
                                "alignment": binding.alignment,
                            },
                            sort_keys=True,
                        ),
                        "digest": binding.fingerprint,
                    },
                )
            connection.execute(
                sa.text(
                    "INSERT INTO platform.template_renderer_assets "
                    "(template_id,template_version,asset_role,asset_version,object_key,media_type,"
                    "byte_length,content_digest,provenance,validation_status,created_at) VALUES "
                    "(:template,:version,'font',1,:object,:media,:length,:digest,CAST(:provenance AS jsonb),"
                    "'qualified',:now) ON CONFLICT DO NOTHING"
                ),
                {
                    "template": template_id,
                    "version": template_version,
                    "object": font_key,
                    "media": font_media_type,
                    "length": len(font_bytes),
                    "digest": font_digest,
                    "provenance": json.dumps(
                        {"role": "renderer-font", "digest": font_digest}, sort_keys=True
                    ),
                    "now": now,
                },
            )
            if required_document_type_id is not None:
                connection.execute(
                    sa.text(
                        "INSERT INTO platform.required_document_type_templates "
                        "(required_document_type_id,required_document_type_version,template_id,"
                        "template_version,applicability_status,mapping_digest,created_at) VALUES "
                        "(:type,:type_version,:template,:template_version,'active',:digest,:now) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "type": required_document_type_id,
                        "type_version": required_document_type_version,
                        "template": template_id,
                        "template_version": template_version,
                        "digest": semantic_digest(
                            {
                                "document_type": str(required_document_type_id),
                                "document_type_version": required_document_type_version,
                                "template": str(template_id),
                                "template_version": template_version,
                            }
                        ),
                        "now": now,
                    },
                )
            observed = (
                connection.execute(
                    sa.text(
                        "SELECT tv.template_digest,q.receipt_digest FROM platform.template_versions tv "
                        "JOIN platform.template_qualification_receipts q ON q.template_id=tv.template_id "
                        "AND q.template_version=tv.version WHERE tv.template_id=:template AND tv.version=:version"
                    ),
                    {"template": template_id, "version": template_version},
                )
                .mappings()
                .one()
            )
            if (
                str(observed["template_digest"]) != receipt.template_digest
                or str(observed["receipt_digest"]) != receipt.fingerprint
            ):
                raise ValueError("template_publication_identity_conflict")
        return QualifiedTemplatePublication(
            source_id,
            template_id,
            template_version,
            schema_id,
            field_schema_version,
            source_key,
            template_key,
            font_key,
            receipt.source_digest,
            receipt.template_digest,
            font_digest,
            receipt.fingerprint,
        )
