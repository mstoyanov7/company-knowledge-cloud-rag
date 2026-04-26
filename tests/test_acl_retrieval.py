from __future__ import annotations

from shared_schemas import AccessScope

from rag_api.adapters.retrieval.qdrant import QdrantAclRetriever


def test_qdrant_acl_filter_includes_tenant_acl_and_source_scope() -> None:
    access_scope = AccessScope(
        user_id="u1",
        email="u1@example.com",
        tenant_id="tenant-1",
        allowed_acl_tags=["public", "engineering"],
        source_filters=["sharepoint"],
    )

    payload_filter = QdrantAclRetriever.build_payload_filter(access_scope).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )

    assert payload_filter["must"][0] == {"key": "tenant_id", "match": {"value": "tenant-1"}}
    assert payload_filter["must"][1] == {"key": "acl_tags", "match": {"any": ["public", "engineering"]}}
    assert payload_filter["must"][2] == {"key": "source_system", "match": {"any": ["sharepoint"]}}
