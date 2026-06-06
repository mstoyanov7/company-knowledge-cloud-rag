import { createRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { UserProfile } from "../api/auth";
import { ProfileMenu } from "./ProfileMenu";

describe("ProfileMenu", () => {
  it("shows administration only for active system admins", () => {
    const admin = renderMenu({ app_role: "system_admin", status: "active" });
    const user = renderMenu({ app_role: "user", status: "active" });

    expect(admin).toContain("Administration");
    expect(user).not.toContain("Administration");
  });
});

function renderMenu(overrides: Partial<UserProfile>): string {
  return renderToStaticMarkup(
    <ProfileMenu
      user={{ ...baseUser(), ...overrides }}
      theme="light"
      anchorRef={createRef<HTMLButtonElement>()}
      onClose={() => undefined}
      onOpenProfile={() => undefined}
      onToggleTheme={() => undefined}
      onOpenPreferences={() => undefined}
      onOpenAdmin={() => undefined}
      onSignOut={() => undefined}
    />
  );
}

function baseUser(): UserProfile {
  return {
    user_id: "usr-1",
    email: "user@example.com",
    name: "User Example",
    tenant_id: "local-tenant",
    acl_tags: ["public"],
    groups: [],
    roles: [],
    role: "Employee",
    dept: "Engineering",
    status: "active",
    app_role: "user",
    created_at_utc: "2026-01-01T00:00:00Z"
  };
}
