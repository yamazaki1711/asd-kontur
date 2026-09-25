#!/usr/bin/env python3
"""Verify NTD consultant inventory and SP 70 visibility on an explicit database."""

# ruff: noqa: RUF001 -- mixed-alphabet designation aliases are verified deliberately.

from __future__ import annotations

import argparse
import json
from uuid import uuid4

from sqlalchemy import create_engine, text

from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.knowledge.gateway import GatewayContext


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    arguments = parser.parse_args()
    engine = create_engine(arguments.database_url)
    try:
        with engine.connect() as connection:
            workspace = connection.execute(
                text(
                    "SELECT organization_id,workspace_id,created_by_identity_id "
                    "FROM workspace.workspaces ORDER BY created_at LIMIT 1"
                )
            ).one()
        context = GatewayContext(
            str(workspace.created_by_identity_id),
            "assistant.chat.verify",
            "ntd-consultant-corpus-verification@1.0.0",
            uuid4(),
            workspace.organization_id,
            workspace.workspace_id,
        )
        query = ProfessionalAssistantKnowledgeQuery(engine)
        resolutions = {}
        for designation in ("СП 70", "СП70", "СП 70.13330", "СП 70.13330.2012"):
            result = query.execute(
                "consultant.resolve_ntd_designation",
                {"mode": "Support", "designation": designation},
                context,
            ).result
            assert result["outcome"] == "document_present_searchable"
            assert result["items"][0]["document"] == "СП 70.13330.2012"
            assert result["items"][0]["verified_provision_count"] == 0
            resolutions[designation] = result["outcome"]
        absent = query.execute(
            "consultant.resolve_ntd_designation",
            {"mode": "Support", "designation": "СП 999.99999.2099"},
            context,
        ).result
        assert absent["outcome"] == "document_not_present"
        content = query.execute(
            "consultant.search_ntd_content",
            {
                "mode": "Support",
                "query": "контроль качества бетона входной операционный приемочный",
                "limit": 5,
            },
            context,
        ).result
        assert any(item["document"] == "СП 70.13330.2012" for item in content["items"])
        assert len({item["document"] for item in content["items"]}) == len(content["items"])
        inventory = query.execute(
            "consultant.get_ntd_inventory", {"mode": "Support"}, context
        ).result["value"]
        assert inventory["official_count"] == 15
        assert inventory["reference_count"] == 104
        assert inventory["verified_provision_count"] == 1294
        print(
            json.dumps(
                {
                    "status": "pass",
                    "resolutions": resolutions,
                    "absent_outcome": absent["outcome"],
                    "content_documents": [item["document"] for item in content["items"]],
                    "inventory": inventory,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
