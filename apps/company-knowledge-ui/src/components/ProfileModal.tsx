import { Badge, Building2, LogOut, Mail, UserRound, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { UserProfile } from "../api/auth";
import { initialsOf } from "../utils/user";

const PROFILE_ROLES = [
  "Employee",
  "People Operations",
  "Finance",
  "Engineering",
  "IT & Security",
  "Product",
  "Sales",
  "Facilities"
];

type ProfileModalProps = {
  user: UserProfile;
  onClose: () => void;
  onSave: (user: UserProfile) => void;
  onSignOut: () => void;
};

export function ProfileModal({ user, onClose, onSave, onSignOut }: ProfileModalProps) {
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState(user.role || user.roles[0] || "Employee");
  const [dept, setDept] = useState(user.dept || "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    onSave({ ...user, name: name.trim(), role, dept });
  }

  return (
    <div className="modal-host">
      <div className="modal__scrim" onClick={onClose} />
      <div className="modal" role="dialog" aria-label="Profile">
        <button className="modal__x" type="button" onClick={onClose} aria-label="Close">
          <X size={17} aria-hidden="true" />
        </button>
        <div className="pmodal__head">
          <span className="p-ava p-ava--xl">{initialsOf(name)}</span>
          <div>
            <h2>{name}</h2>
            <div className="pmodal__meta">
              <span>
                <Mail size={13} aria-hidden="true" /> {user.email}
              </span>
              <span>
                <Badge size={13} aria-hidden="true" /> {role}
              </span>
            </div>
          </div>
        </div>

        <div className="pmodal__stats">
          <div className="pstat">
            <b>{user.acl_tags.length}</b>
            <span>ACL tags</span>
          </div>
          <div className="pstat">
            <b>{user.tenant_id}</b>
            <span>Tenant</span>
          </div>
          <div className="pstat">
            <b>{memberSince(user.created_at_utc)}</b>
            <span>Member since</span>
          </div>
        </div>

        <form className="pmodal__form" onSubmit={handleSubmit}>
          <label className="fld">
            <span className="fld__lbl">Display name</span>
            <span className="fld__box">
              <span className="fld__ico">
                <UserRound size={16} aria-hidden="true" />
              </span>
              <input className="fld__in" value={name} onChange={(event) => setName(event.target.value)} />
            </span>
          </label>
          <label className="fld">
            <span className="fld__lbl">Work email</span>
            <span className="fld__box">
              <span className="fld__ico">
                <Mail size={16} aria-hidden="true" />
              </span>
              <input className="fld__in" type="email" value={user.email} readOnly />
            </span>
          </label>
          <label className="fld">
            <span className="fld__lbl">Role</span>
            <span className="fld__box">
              <span className="fld__ico">
                <Badge size={16} aria-hidden="true" />
              </span>
              <select className="fld__in fld__sel" value={role} onChange={(event) => setRole(event.target.value)}>
                {PROFILE_ROLES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </span>
          </label>
          <label className="fld">
            <span className="fld__lbl">Department</span>
            <span className="fld__box">
              <span className="fld__ico">
                <Building2 size={16} aria-hidden="true" />
              </span>
              <input className="fld__in" value={dept} onChange={(event) => setDept(event.target.value)} />
            </span>
          </label>
          <div className="pmodal__actions">
            <button className="btn" type="button" onClick={onSignOut}>
              <LogOut size={14} aria-hidden="true" /> Sign out
            </button>
            <div className="topbar__spacer" />
            <button className="btn" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn--accent" type="submit">
              Save changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function memberSince(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" }).format(date);
}

