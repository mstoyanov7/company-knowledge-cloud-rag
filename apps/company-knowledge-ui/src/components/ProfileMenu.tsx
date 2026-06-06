import { LogOut, Moon, ShieldCheck, Settings, Sun, UserRound } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";

import type { UserProfile } from "../api/auth";
import type { Theme } from "../state/theme";
import { initialsOf } from "../utils/user";

type ProfileMenuProps = {
  user: UserProfile;
  theme: Theme;
  anchorRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onOpenProfile: () => void;
  onToggleTheme: () => void;
  onOpenPreferences: () => void;
  onOpenAdmin: () => void;
  onSignOut: () => void;
};

export function ProfileMenu({
  user,
  theme,
  anchorRef,
  onClose,
  onOpenProfile,
  onToggleTheme,
  onOpenPreferences,
  onOpenAdmin,
  onSignOut
}: ProfileMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<CSSProperties>({});

  useLayoutEffect(() => {
    function updatePosition() {
      const anchor = anchorRef.current;
      if (!anchor) {
        return;
      }

      const rect = anchor.getBoundingClientRect();
      const width = 252;
      const gutter = 12;
      setPosition({
        left: Math.max(gutter, Math.min(rect.left, window.innerWidth - width - gutter)),
        bottom: Math.max(gutter, window.innerHeight - rect.top + 8)
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorRef]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || anchorRef.current?.contains(target)) {
        return;
      }
      onClose();
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [anchorRef, onClose]);

  return (
    <div ref={menuRef} className="pmenu is-open" role="menu" style={position}>
      <div className="pmenu__id">
        <span className="p-ava">{initialsOf(user.name)}</span>
        <div className="pmenu__idmain">
          <b>{user.name}</b>
          <span>{user.email}</span>
        </div>
      </div>
      <div className="pmenu__rolepill">{user.role || user.dept || user.roles[0] || "Employee"}</div>
      <div className="pmenu__div" />
      <button className="pmenu__item" type="button" onClick={onOpenProfile} role="menuitem">
        <UserRound size={16} aria-hidden="true" /> <span>Account &amp; profile</span>
      </button>
      <button className="pmenu__item" type="button" onClick={onToggleTheme} role="menuitem">
        {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}{" "}
        <span>Switch to {theme === "dark" ? "light" : "dark"} mode</span>
      </button>
      <button className="pmenu__item" type="button" onClick={onOpenPreferences} role="menuitem">
        <Settings size={16} aria-hidden="true" /> <span>Preferences</span>
      </button>
      {user.app_role === "system_admin" && user.status === "active" ? (
        <button className="pmenu__item" type="button" onClick={onOpenAdmin} role="menuitem">
          <ShieldCheck size={16} aria-hidden="true" /> <span>Administration</span>
        </button>
      ) : null}
      <div className="pmenu__div" />
      <button className="pmenu__item pmenu__item--danger" type="button" onClick={onSignOut} role="menuitem">
        <LogOut size={16} aria-hidden="true" /> <span>Sign out</span>
      </button>
    </div>
  );
}
