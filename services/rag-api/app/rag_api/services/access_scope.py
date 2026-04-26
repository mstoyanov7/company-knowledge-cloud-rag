from __future__ import annotations

from shared_schemas import AccessScope, UserContext


class AccessScopeResolver:
    def resolve(self, user_context: UserContext, source_filters: list[str] | None = None) -> AccessScope:
        allowed_acl_tags = sorted({tag.strip() for tag in user_context.acl_tags if tag.strip()})
        return AccessScope(
            user_id=user_context.user_id,
            email=user_context.email,
            tenant_id=user_context.tenant_id,
            allowed_acl_tags=allowed_acl_tags,
            groups=sorted({group.strip() for group in user_context.groups if group.strip()}),
            roles=sorted({role.strip() for role in user_context.roles if role.strip()}),
            source_filters=sorted({source.strip() for source in (source_filters or []) if source.strip()}),
        )
