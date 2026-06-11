import {
  Badge,
  Building2,
  ChevronDown,
  Check,
  Layers,
  Palette,
  Plus,
  Save,
  ShieldCheck,
  UserRound,
  Users,
  X
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  activateUser,
  approveUser,
  createAdminTopic,
  disableAdminTopic,
  fetchAdminTopics,
  fetchAdminUsers,
  rejectUser,
  suspendUser,
  updateAdminTopic,
  updateAdminUser,
  updateUiSettings,
  type UiSettings
} from "../api/admin";
import type { UserProfile } from "../api/auth";
import type { TopicAdmin } from "../api/topics";
import { getTopicIcon, TOPIC_ICON_OPTIONS } from "./topicIcon";
import { useToast } from "./ToastProvider";

type AdminPanelProps = {
  currentUser: UserProfile;
  uiSettings: UiSettings;
  onClose: () => void;
  onTopicsChanged: () => void;
  onUiSettingsChanged: (settings: UiSettings) => void;
};

type UserDraft = {
  name: string;
  app_role: UserProfile["app_role"];
  role: string;
  dept: string;
  acl_tags: string;
};

type TopicDraft = {
  id: string;
  name: string;
  description: string;
  icon: string;
  acl_tags: string;
  retrieval_tags: string;
  suggested_questions: string;
  enabled: boolean;
};

const BLANK_TOPIC: TopicDraft = {
  id: "",
  name: "",
  description: "",
  icon: "layers",
  acl_tags: "public,employees",
  retrieval_tags: "",
  suggested_questions: "",
  enabled: true
};

const APP_ROLE_OPTIONS: Array<{ value: UserProfile["app_role"]; label: string }> = [
  { value: "user", label: "Standard user" },
  { value: "system_admin", label: "System administrator" }
];

const DEPARTMENT_OPTIONS = [
  "People & HR",
  "Finance",
  "Engineering",
  "IT & Security",
  "Product",
  "Sales",
  "Operations",
  "Legal",
  "Procurement",
  "Customer Success",
  "Facilities"
];

const DISPLAY_ROLE_OPTIONS = [
  "Employee",
  "Engineer",
  "Senior Engineer",
  "Engineering Manager",
  "Product Manager",
  "Designer",
  "People Operations",
  "Finance",
  "IT & Security",
  "Security Analyst",
  "Sales",
  "Operations",
  "Facilities",
  "Contractor"
];

export function AdminPanel({
  currentUser,
  uiSettings,
  onClose,
  onTopicsChanged,
  onUiSettingsChanged
}: AdminPanelProps) {
  const { toast } = useToast();
  const [tab, setTab] = useState<"users" | "topics" | "branding">("users");
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [topics, setTopics] = useState<TopicAdmin[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [userDraft, setUserDraft] = useState<UserDraft | null>(null);
  const [topicDraft, setTopicDraft] = useState<TopicDraft>(BLANK_TOPIC);
  const [isNewTopic, setIsNewTopic] = useState(false);
  const [brandDraft, setBrandDraft] = useState({
    app_name: uiSettings.app_name,
    app_subtitle: uiSettings.app_subtitle,
    accent_hue: String(uiSettings.accent_hue),
    logo_url: uiSettings.logo_url || "",
    logo_text: uiSettings.logo_text || ""
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isIconMenuOpen, setIsIconMenuOpen] = useState(false);

  useEffect(() => {
    let current = true;
    Promise.all([fetchAdminUsers(), fetchAdminTopics()])
      .then(([nextUsers, nextTopics]) => {
        if (!current) {
          return;
        }
        setUsers(nextUsers);
        setTopics(nextTopics);
        const firstUser = nextUsers[0] || null;
        const firstTopic = nextTopics[0] || null;
        setSelectedUserId(firstUser?.user_id || null);
        setUserDraft(firstUser ? draftFromUser(firstUser) : null);
        setSelectedTopicId(firstTopic?.id || null);
        setTopicDraft(firstTopic ? draftFromTopic(firstTopic) : BLANK_TOPIC);
      })
      .catch((error: Error) => toast(error.message, "err"))
      .finally(() => {
        if (current) {
          setIsLoading(false);
        }
      });
    return () => {
      current = false;
    };
  }, [toast]);

  const selectedUser = useMemo(
    () => users.find((candidate) => candidate.user_id === selectedUserId) || null,
    [selectedUserId, users]
  );

  const selectedTopic = useMemo(
    () => topics.find((candidate) => candidate.id === selectedTopicId) || null,
    [selectedTopicId, topics]
  );

  async function runUserAction(action: () => Promise<UserProfile>, message: string) {
    setIsSaving(true);
    try {
      const updated = await action();
      setUsers((current) => replaceUser(current, updated));
      setSelectedUserId(updated.user_id);
      setUserDraft(draftFromUser(updated));
      toast(message, "ok");
    } catch (error) {
      toast(error instanceof Error ? error.message : "User update failed.", "err");
    } finally {
      setIsSaving(false);
    }
  }

  function selectUser(user: UserProfile) {
    setSelectedUserId(user.user_id);
    setUserDraft(draftFromUser(user));
  }

  function selectTopic(topic: TopicAdmin) {
    setIsNewTopic(false);
    setIsIconMenuOpen(false);
    setSelectedTopicId(topic.id);
    setTopicDraft(draftFromTopic(topic));
  }

  function startNewTopic() {
    setIsNewTopic(true);
    setIsIconMenuOpen(false);
    setSelectedTopicId(null);
    setTopicDraft(BLANK_TOPIC);
  }

  async function saveUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser || !userDraft) {
      return;
    }
    await runUserAction(
      () =>
        updateAdminUser(selectedUser.user_id, {
          name: userDraft.name,
          app_role: userDraft.app_role,
          role: emptyToNull(userDraft.role),
          dept: emptyToNull(userDraft.dept),
          acl_tags: splitCsv(userDraft.acl_tags)
        }),
      "User updated."
    );
  }

  async function saveTopic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!topicDraft.id.trim() || !topicDraft.name.trim() || !topicDraft.description.trim()) {
      toast("Topic id, name, and description are required.", "err");
      return;
    }
    setIsSaving(true);
    const request = {
      name: topicDraft.name.trim(),
      description: topicDraft.description.trim(),
      icon: emptyToNull(topicDraft.icon),
      acl_tags: splitCsv(topicDraft.acl_tags),
      retrieval_tags: splitCsv(topicDraft.retrieval_tags),
      suggested_questions: splitLines(topicDraft.suggested_questions),
      enabled: topicDraft.enabled
    };
    try {
      const saved = isNewTopic
        ? await createAdminTopic({ id: topicDraft.id.trim(), ...request })
        : await updateAdminTopic(topicDraft.id, request);
      setTopics((current) => replaceTopic(current, saved));
      setSelectedTopicId(saved.id);
      setTopicDraft(draftFromTopic(saved));
      setIsNewTopic(false);
      onTopicsChanged();
      toast("Topic saved.", "ok");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Topic save failed.", "err");
    } finally {
      setIsSaving(false);
    }
  }

  async function disableTopic() {
    if (!selectedTopic) {
      return;
    }
    setIsSaving(true);
    try {
      const saved = await disableAdminTopic(selectedTopic.id);
      setTopics((current) => replaceTopic(current, saved));
      setTopicDraft(draftFromTopic(saved));
      onTopicsChanged();
      toast("Topic disabled.", "ok");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Topic update failed.", "err");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveBranding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    try {
      const saved = await updateUiSettings({
        app_name: brandDraft.app_name.trim(),
        app_subtitle: brandDraft.app_subtitle.trim(),
        accent_hue: Number(brandDraft.accent_hue),
        logo_url: emptyToNull(brandDraft.logo_url),
        logo_text: emptyToNull(brandDraft.logo_text)
      });
      onUiSettingsChanged(saved);
      toast("Branding saved.", "ok");
    } catch (error) {
      toast(error instanceof Error ? error.message : "Branding save failed.", "err");
    } finally {
      setIsSaving(false);
    }
  }

  const TopicDraftIcon = getTopicIcon(topicDraft.icon);
  const selectedIconLabel =
    TOPIC_ICON_OPTIONS.find((option) => option.id === topicDraft.icon)?.label || "Notebook";

  return (
    <div className="modal-host">
      <div className="modal__scrim" onClick={onClose} />
      <div className="modal modal--admin" role="dialog" aria-label="Administration">
        <button className="modal__x" type="button" onClick={onClose} aria-label="Close">
          <X size={17} aria-hidden="true" />
        </button>
        <div className="admin__head">
          <span className="admin__mark">
            <ShieldCheck size={20} aria-hidden="true" />
          </span>
          <div>
            <h2>Administration</h2>
            <span>{currentUser.email}</span>
          </div>
        </div>

        <div className="admin__tabs" role="tablist">
          <button type="button" className={tab === "users" ? "is-active" : ""} onClick={() => setTab("users")}>
            <Users size={14} aria-hidden="true" /> Users
          </button>
          <button type="button" className={tab === "topics" ? "is-active" : ""} onClick={() => setTab("topics")}>
            <Layers size={14} aria-hidden="true" /> Topics
          </button>
          <button type="button" className={tab === "branding" ? "is-active" : ""} onClick={() => setTab("branding")}>
            <Palette size={14} aria-hidden="true" /> Branding
          </button>
        </div>

        {isLoading ? (
          <div className="admin__loading">Loading administration data</div>
        ) : (
          <div className="admin__body">
            {tab === "users" ? (
              <div className="admin-grid">
                <div className="admin-list scroll">
                  {users.map((user) => (
                    <button
                      key={user.user_id}
                      className={userRowClassName(user, selectedUserId)}
                      type="button"
                      onClick={() => selectUser(user)}
                    >
                      <span className={`status-dot status-dot--${user.status}`} />
                      <span>
                        <b>{user.name}</b>
                        <small>{user.email}</small>
                      </span>
                      <em>{user.status}</em>
                    </button>
                  ))}
                </div>

                {selectedUser && userDraft ? (
                  <form
                    className={selectedUser.status === "suspended" ? "admin-form admin-form--suspended scroll" : "admin-form scroll"}
                    onSubmit={saveUser}
                  >
                    <div className="admin-form__title">
                      <div>
                        <h3>{selectedUser.name}</h3>
                        <span>{selectedUser.email}</span>
                      </div>
                      <span className={`admin-status admin-status--${selectedUser.status}`}>
                        {selectedUser.status}
                      </span>
                    </div>
                    <label className="fld">
                      <span className="fld__lbl">Display name</span>
                      <span className="fld__box">
                        <span className="fld__ico">
                          <UserRound size={16} aria-hidden="true" />
                        </span>
                        <input className="fld__in" value={userDraft.name} onChange={(event) => setUserDraft({ ...userDraft, name: event.target.value })} />
                      </span>
                    </label>
                    <div className="admin-form__two">
                      <label className="fld">
                        <span className="fld__lbl">App role</span>
                        <span className="fld__box">
                          <select
                            className="fld__in fld__sel"
                            value={userDraft.app_role}
                            onChange={(event) => setUserDraft({ ...userDraft, app_role: event.target.value as UserProfile["app_role"] })}
                          >
                            {APP_ROLE_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
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
                          <select
                            className="fld__in fld__sel"
                            value={userDraft.dept}
                            onChange={(event) => setUserDraft({ ...userDraft, dept: event.target.value })}
                          >
                            <option value="">No department</option>
                            {optionsWithCurrent(DEPARTMENT_OPTIONS, userDraft.dept).map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </span>
                      </label>
                    </div>
                    <div className="admin-form__two">
                      <label className="fld">
                        <span className="fld__lbl">Display role</span>
                        <span className="fld__box">
                          <span className="fld__ico">
                            <Badge size={16} aria-hidden="true" />
                          </span>
                          <select
                            className="fld__in fld__sel"
                            value={userDraft.role}
                            onChange={(event) => setUserDraft({ ...userDraft, role: event.target.value })}
                          >
                            <option value="">No display role</option>
                            {optionsWithCurrent(DISPLAY_ROLE_OPTIONS, userDraft.role).map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        </span>
                      </label>
                      <label className="fld">
                        <span className="fld__lbl">ACL tags</span>
                        <span className="fld__box">
                          <input className="fld__in" value={userDraft.acl_tags} onChange={(event) => setUserDraft({ ...userDraft, acl_tags: event.target.value })} />
                        </span>
                      </label>
                    </div>
                    <div className="admin-actions">
                      {selectedUser.status === "pending" ? (
                        <>
                          <button className="btn" type="button" disabled={isSaving} onClick={() => runUserAction(() => approveUser(selectedUser.user_id), "User approved.")}>
                            <Check size={14} aria-hidden="true" /> Approve
                          </button>
                          <button className="btn btn--danger" type="button" disabled={isSaving} onClick={() => runUserAction(() => rejectUser(selectedUser.user_id), "User rejected.")}>
                            Reject
                          </button>
                        </>
                      ) : null}
                      {selectedUser.status === "active" ? (
                        <button className="btn btn--danger" type="button" disabled={isSaving} onClick={() => runUserAction(() => suspendUser(selectedUser.user_id), "User suspended.")}>
                          Suspend
                        </button>
                      ) : null}
                      {selectedUser.status === "suspended" ? (
                        <button className="btn btn--accent" type="button" disabled={isSaving} onClick={() => runUserAction(() => activateUser(selectedUser.user_id), "User activated.")}>
                          <Check size={14} aria-hidden="true" /> Activate
                        </button>
                      ) : null}
                      <span className="topbar__spacer" />
                      <button className="btn btn--accent" type="submit" disabled={isSaving}>
                        <Save size={14} aria-hidden="true" /> Save
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
            ) : null}

            {tab === "topics" ? (
              <div className="admin-grid">
                <div className="admin-list scroll">
                  <button className="admin-row admin-row--new" type="button" onClick={startNewTopic}>
                    <Plus size={14} aria-hidden="true" />
                    <span>
                      <b>New topic</b>
                      <small>Create topic</small>
                    </span>
                  </button>
                  {topics.map((topic) => (
                    <button
                      key={topic.id}
                      className={topic.id === selectedTopicId ? "admin-row is-active" : "admin-row"}
                      type="button"
                      onClick={() => selectTopic(topic)}
                    >
                      <span className={`status-dot ${topic.enabled ? "status-dot--active" : "status-dot--suspended"}`} />
                      <span>
                        <b>{topic.name}</b>
                        <small>{topic.id}</small>
                      </span>
                      <em>{topic.enabled ? "enabled" : "disabled"}</em>
                    </button>
                  ))}
                </div>

                <form className="admin-form scroll" onSubmit={saveTopic}>
                  <div className="admin-form__two">
                    <label className="fld">
                      <span className="fld__lbl">Topic id</span>
                      <span className="fld__box">
                        <input className="fld__in" value={topicDraft.id} readOnly={!isNewTopic} onChange={(event) => setTopicDraft({ ...topicDraft, id: event.target.value })} />
                      </span>
                    </label>
                    <label className="fld">
                      <span className="fld__lbl">Icon</span>
                      <div className="icon-picker-wrap">
                        <button
                          className="icon-picker"
                          type="button"
                          aria-haspopup="menu"
                          aria-expanded={isIconMenuOpen}
                          onClick={() => setIsIconMenuOpen((current) => !current)}
                        >
                          <span className="icon-picker__mark">
                            <TopicDraftIcon size={16} aria-hidden="true" />
                          </span>
                          <span className="icon-picker__text">
                            <b>{selectedIconLabel}</b>
                            <small>{topicDraft.icon || "notebook-tabs"}</small>
                          </span>
                          <ChevronDown size={15} aria-hidden="true" />
                        </button>
                        {isIconMenuOpen ? (
                          <div className="icon-menu" role="menu">
                            {TOPIC_ICON_OPTIONS.map((option) => (
                              <button
                                key={option.id}
                                className={option.id === topicDraft.icon ? "icon-menu__item is-active" : "icon-menu__item"}
                                type="button"
                                role="menuitemradio"
                                aria-checked={option.id === topicDraft.icon}
                                onClick={() => {
                                  setTopicDraft({ ...topicDraft, icon: option.id });
                                  setIsIconMenuOpen(false);
                                }}
                              >
                                <span className="icon-menu__mark">
                                  <option.Icon size={15} aria-hidden="true" />
                                </span>
                                <span>{option.label}</span>
                                {option.id === topicDraft.icon ? <Check size={14} aria-hidden="true" /> : null}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </label>
                  </div>
                  <label className="fld">
                    <span className="fld__lbl">Name</span>
                    <span className="fld__box">
                      <input className="fld__in" value={topicDraft.name} onChange={(event) => setTopicDraft({ ...topicDraft, name: event.target.value })} />
                    </span>
                  </label>
                  <label className="fld">
                    <span className="fld__lbl">Description</span>
                    <textarea className="admin-textarea" value={topicDraft.description} onChange={(event) => setTopicDraft({ ...topicDraft, description: event.target.value })} />
                  </label>
                  <label className="fld">
                    <span className="fld__lbl">ACL tags</span>
                    <span className="fld__box">
                      <input className="fld__in" value={topicDraft.acl_tags} onChange={(event) => setTopicDraft({ ...topicDraft, acl_tags: event.target.value })} />
                    </span>
                  </label>
                  <label className="fld">
                    <span className="fld__lbl">Retrieval tags</span>
                    <span className="fld__box">
                      <input className="fld__in" value={topicDraft.retrieval_tags} onChange={(event) => setTopicDraft({ ...topicDraft, retrieval_tags: event.target.value })} />
                    </span>
                  </label>
                  <label className="fld">
                    <span className="fld__lbl">Suggested questions</span>
                    <textarea className="admin-textarea admin-textarea--tall" value={topicDraft.suggested_questions} onChange={(event) => setTopicDraft({ ...topicDraft, suggested_questions: event.target.value })} />
                  </label>
                  <label className="admin-check">
                    <input type="checkbox" checked={topicDraft.enabled} onChange={(event) => setTopicDraft({ ...topicDraft, enabled: event.target.checked })} />
                    <span>Enabled</span>
                  </label>
                  <div className="admin-actions">
                    {!isNewTopic && selectedTopic ? (
                      <button className="btn" type="button" disabled={isSaving} onClick={disableTopic}>
                        Disable
                      </button>
                    ) : null}
                    <span className="topbar__spacer" />
                    <button className="btn btn--accent" type="submit" disabled={isSaving}>
                      <Save size={14} aria-hidden="true" /> Save topic
                    </button>
                  </div>
                </form>
              </div>
            ) : null}

            {tab === "branding" ? (
              <form className="admin-form admin-form--branding" onSubmit={saveBranding}>
                <label className="fld">
                  <span className="fld__lbl">App name</span>
                  <span className="fld__box">
                    <input className="fld__in" value={brandDraft.app_name} onChange={(event) => setBrandDraft({ ...brandDraft, app_name: event.target.value })} />
                  </span>
                </label>
                <label className="fld">
                  <span className="fld__lbl">Subtitle</span>
                  <span className="fld__box">
                    <input className="fld__in" value={brandDraft.app_subtitle} onChange={(event) => setBrandDraft({ ...brandDraft, app_subtitle: event.target.value })} />
                  </span>
                </label>
                <label className="fld">
                  <span className="fld__lbl">Accent hue</span>
                  <span className="fld__box">
                    <input className="fld__in" type="number" min={0} max={360} value={brandDraft.accent_hue} onChange={(event) => setBrandDraft({ ...brandDraft, accent_hue: event.target.value })} />
                  </span>
                </label>
                <label className="fld">
                  <span className="fld__lbl">Logo URL</span>
                  <span className="fld__box">
                    <input className="fld__in" value={brandDraft.logo_url} onChange={(event) => setBrandDraft({ ...brandDraft, logo_url: event.target.value })} />
                  </span>
                </label>
                <label className="fld">
                  <span className="fld__lbl">Text mark</span>
                  <span className="fld__box">
                    <input className="fld__in" value={brandDraft.logo_text} onChange={(event) => setBrandDraft({ ...brandDraft, logo_text: event.target.value })} />
                  </span>
                </label>
                <div className="admin-actions">
                  <span className="topbar__spacer" />
                  <button className="btn btn--accent" type="submit" disabled={isSaving}>
                    <Save size={14} aria-hidden="true" /> Save branding
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function draftFromUser(user: UserProfile): UserDraft {
  return {
    name: user.name,
    app_role: user.app_role,
    role: user.role || "",
    dept: user.dept || "",
    acl_tags: user.acl_tags.join(",")
  };
}

function draftFromTopic(topic: TopicAdmin): TopicDraft {
  return {
    id: topic.id,
    name: topic.name,
    description: topic.description,
    icon: topic.icon || "notebook-tabs",
    acl_tags: topic.acl_tags.join(","),
    retrieval_tags: topic.retrieval_tags.join(","),
    suggested_questions: topic.suggested_questions.join("\n"),
    enabled: topic.enabled
  };
}

function replaceUser(users: UserProfile[], updated: UserProfile): UserProfile[] {
  const next = users.map((user) => (user.user_id === updated.user_id ? updated : user));
  return next.sort((left, right) => statusRank(left.status) - statusRank(right.status) || left.email.localeCompare(right.email));
}

function replaceTopic(topics: TopicAdmin[], updated: TopicAdmin): TopicAdmin[] {
  const exists = topics.some((topic) => topic.id === updated.id);
  const next = exists ? topics.map((topic) => (topic.id === updated.id ? updated : topic)) : [updated, ...topics];
  return next.sort((left, right) => left.name.localeCompare(right.name));
}

function userRowClassName(user: UserProfile, selectedUserId: string | null): string {
  const classes = ["admin-row"];
  if (user.user_id === selectedUserId) {
    classes.push("is-active");
  }
  if (user.status === "suspended") {
    classes.push("admin-row--suspended");
  }
  return classes.join(" ");
}

function statusRank(status: UserProfile["status"]): number {
  return { pending: 0, active: 1, suspended: 2, rejected: 3 }[status] ?? 9;
}

function optionsWithCurrent(options: string[], current: string): string[] {
  const trimmed = current.trim();
  if (!trimmed || options.includes(trimmed)) {
    return options;
  }
  return [trimmed, ...options];
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}
