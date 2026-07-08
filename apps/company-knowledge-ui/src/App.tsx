import { useEffect, useMemo, useState } from "react";

import { fetchMe, logout, updateMe, type AuthResponse, type UserProfile } from "./api/auth";
import { fetchUiSettings, type UiSettings } from "./api/admin";
import { clearAuthToken, getAuthToken } from "./api/client";
import { ALL_TOPICS_TOPIC, fetchTopics, type Topic } from "./api/topics";
import { AuthGate } from "./components/AuthGate";
import { ErrorState } from "./components/ErrorState";
import { KnowledgeShell } from "./components/KnowledgeShell";
import { LoadingState } from "./components/LoadingState";
import { useToast } from "./components/ToastProvider";
import { applyPrefs, loadPrefs, savePrefs, type AccentHue, type Density, type Prefs } from "./state/prefs";
import { setUserScope } from "./state/scope";
import { loadTheme, nextTheme, saveTheme, type Theme } from "./state/theme";

const DEFAULT_UI_SETTINGS: UiSettings = {
  app_name: "Company Knowledge",
  app_subtitle: "Assistant",
  accent_hue: 45,
  logo_url: null,
  logo_text: null
};

export default function App() {
  const { toast } = useToast();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadTheme());
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs());
  const [user, setUser] = useState<UserProfile | null>(null);
  const [uiSettings, setUiSettings] = useState<UiSettings>(DEFAULT_UI_SETTINGS);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveTheme(theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.style.setProperty("--accent-h", String(uiSettings.accent_hue));
    document.title = uiSettings.app_subtitle ? `${uiSettings.app_name} - ${uiSettings.app_subtitle}` : uiSettings.app_name;
  }, [uiSettings]);

  useEffect(() => {
    applyPrefs(prefs);
    savePrefs(prefs);
  }, [prefs]);

  useEffect(() => {
    let isCurrent = true;
    fetchUiSettings()
      .then((settings) => {
        if (isCurrent) {
          setUiSettings(settings);
        }
      })
      .catch(() => undefined);
    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    if (!getAuthToken()) {
      setIsAuthLoading(false);
      return;
    }
    let isCurrent = true;
    fetchMe()
      .then((profile) => {
        if (isCurrent) {
          setUserScope(profile.user_id);
          setUser(profile);
        }
      })
      .catch(() => {
        if (isCurrent) {
          clearAuthToken();
          setUser(null);
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsAuthLoading(false);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  useEffect(() => {
    let isCurrent = true;

    refreshTopics()
      .catch(() => undefined)
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  // "Everything" is always offered first, ahead of the real topics.
  const visibleTopics = useMemo(() => [ALL_TOPICS_TOPIC, ...topics], [topics]);

  const selectedTopic = useMemo(
    () => visibleTopics.find((topic) => topic.id === selectedTopicId) || null,
    [selectedTopicId, visibleTopics]
  );

  useEffect(() => {
    if (selectedTopicId && !visibleTopics.some((topic) => topic.id === selectedTopicId)) {
      setSelectedTopicId(null);
    }
  }, [selectedTopicId, visibleTopics]);

  function signIn(response: AuthResponse, message: string) {
    setUserScope(response.user.user_id);
    setUser(response.user);
    refreshTopics().catch((refreshError: Error) => toast(refreshError.message, "err"));
    toast(message, "ok");
  }

  function signOut() {
    logout().catch(() => undefined);
    setUserScope(null);
    setUser(null);
    setSelectedTopicId(null);
  }

  function updateUser(nextUser: UserProfile) {
    updateMe({
      name: nextUser.name,
      role: nextUser.role,
      dept: nextUser.dept
    })
      .then((profile) => {
        setUser(profile);
        toast("Profile updated.", "ok");
      })
      .catch((updateError: Error) => toast(updateError.message, "err"));
  }

  async function refreshTopics() {
    try {
      const items = await fetchTopics();
      setTopics(items);
      setError(null);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Topics are unavailable.";
      setError(message);
      throw new Error(message);
    }
  }

  if (isAuthLoading) {
    return <LoadingState label="Checking session" />;
  }

  if (!user) {
    return <AuthGate onSignIn={signIn} uiSettings={uiSettings} />;
  }

  if (isLoading) {
    return <LoadingState label="Loading knowledge topics" />;
  }

  if (error) {
    return (
      <main className="app-shell app-shell--centered">
        <ErrorState title="Topics are unavailable" message={error} />
      </main>
    );
  }

  return (
    <KnowledgeShell
      key={user.user_id}
      topics={visibleTopics}
      selectedTopic={selectedTopic}
      theme={theme}
      prefs={prefs}
      user={user}
      uiSettings={uiSettings}
      onSelectTopic={setSelectedTopicId}
      onClearTopic={() => setSelectedTopicId(null)}
      onToggleTheme={() => setTheme((currentTheme) => nextTheme(currentTheme))}
      onSetTheme={setTheme}
      onSetDensity={(density: Density) => setPrefs((current) => ({ ...current, density }))}
      onSetAccent={(accentHue: AccentHue) => setPrefs((current) => ({ ...current, accentHue }))}
      onSignOut={signOut}
      onUpdateUser={updateUser}
      onTopicsChanged={() => refreshTopics().catch((refreshError: Error) => toast(refreshError.message, "err"))}
      onUiSettingsChanged={setUiSettings}
    />
  );
}
