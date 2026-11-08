import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import type { Schemas } from "../../api/client";
import { auth } from "../../api/endpoints";
import { dashboardKey, meKey, TimezoneForm } from "../../app/AppShell";
import { useAuth } from "../../auth/AuthContext";
import { ChangePasswordForm } from "../../auth/PasswordPages";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { Icon } from "../../components/Icon";
import { getTheme, setTheme, type Theme } from "../../theme";
import { LANGUAGES, useI18n, type Language } from "../../i18n";

type User = Schemas["UserRead"];

const SECTIONS = [
  { id: "settings-profile-section", label: "settings.profile" },
  { id: "settings-community-section", label: "settings.community" },
  { id: "settings-language-section", label: "settings.language" },
  { id: "settings-appearance-section", label: "settings.appearance" },
  { id: "settings-study-section", label: "settings.study" },
  { id: "settings-security-section", label: "settings.security" },
] as const;

/** Profile, interface language, study preferences and security, saved to the account. */
export function SettingsPage() {
  const { t } = useI18n();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  return (
    <div className="page settings-page">
      <div className="page-header">
        <h1>{t("settings.title")}</h1>
        <p className="hint">{t("settings.intro")}</p>
      </div>
      <QueryState query={me}>
        {(user) => (
          <>
            <nav className="settings-nav" aria-label={t("settings.sections")}>
              {SECTIONS.map((section) => (
                <a key={section.id} href={`#${section.id}`}>
                  {t(section.label)}
                </a>
              ))}
            </nav>
            <ProfileSection user={user} />
            <CommunitySection user={user} />
            <LanguageSection user={user} />
            <AppearanceSection />
            <section className="card settings-section" id="settings-study-section" aria-labelledby="settings-study">
              <h2 id="settings-study">{t("settings.study")}</h2>
              <TimezoneForm current={user.timezone} />
              <p className="hint">{t("settings.timezoneHint")}</p>
              <DailyGoalForm current={user.daily_goal} />
            </section>
            <SecuritySection />
          </>
        )}
      </QueryState>
    </div>
  );
}

function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["UserPreferencesUpdate"]) => auth.updateMe(body),
    onSuccess: (user) => {
      queryClient.setQueryData(meKey, user);
      void queryClient.invalidateQueries({ queryKey: dashboardKey });
    },
  });
}

/** Opt in or out of the leaderboards, search and following. Off until the user turns it on. */
function CommunitySection({ user }: { user: User }) {
  const { t } = useI18n();
  const save = useSaveProfile();
  const id = useId();
  return (
    <section className="card settings-section" id="settings-community-section" aria-labelledby="settings-community">
      <h2 id="settings-community">{t("settings.community")}</h2>
      <label className="toggle" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={user.community_visible}
          disabled={save.isPending || (!user.community_visible && !user.display_name)}
          onChange={(e) => save.mutate({ community_visible: e.target.checked })}
        />
        {t("settings.communityToggle")}
      </label>
      <p className="hint">{t("settings.communityHint")}</p>
      {!user.display_name && <p className="hint">{t("community.needName")}</p>}
      <ErrorBanner error={save.error} />
    </section>
  );
}

function ProfileSection({ user }: { user: User }) {
  const { t } = useI18n();
  const save = useSaveProfile();
  const [name, setName] = useState(user.display_name ?? "");
  const [username, setUsername] = useState(user.username ?? "");
  const nameId = useId();
  const usernameId = useId();
  const nameChanged = name !== (user.display_name ?? "");
  const usernameChanged = username.trim().toLowerCase() !== (user.username ?? "");
  // One Save for the whole profile; only what changed is sent.
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({
      ...(nameChanged ? { display_name: name } : {}),
      ...(usernameChanged ? { username: username.trim() } : {}),
    });
  };
  const initial = (user.display_name || user.email)[0]?.toUpperCase();
  return (
    <section className="card settings-section" id="settings-profile-section" aria-labelledby="settings-profile">
      <h2 id="settings-profile">{t("settings.profile")}</h2>
      <div className="profile-row">
        <span className="profile-avatar" aria-hidden="true">
          {initial}
        </span>
        <div>
          <strong>{user.display_name || user.email}</strong>
          {user.display_name && <p className="hint">{user.email}</p>}
        </div>
      </div>
      <form onSubmit={submit} className="settings-form">
        <label htmlFor={nameId}>{t("settings.displayName")}</label>
        <input id={nameId} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
        <p className="hint">{t("settings.displayNameHint")}</p>
        <label htmlFor={usernameId}>{t("settings.username")}</label>
        <input
          id={usernameId}
          value={username}
          maxLength={30}
          autoCapitalize="none"
          spellCheck={false}
          onChange={(e) => setUsername(e.target.value)}
        />
        <p className="hint">{t("settings.usernameHint")}</p>
        <div className="actions">
          <button type="submit" className="primary" disabled={save.isPending || !(nameChanged || usernameChanged)}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
          {save.isSuccess && <span role="status" className="hint">{t("common.saved")}</span>}
        </div>
        <ErrorBanner error={save.error} />
      </form>
      <dl className="settings-facts">
        <dt>{t("settings.email")}</dt>
        <dd>
          {user.email}
          <span className="hint"> · {t("settings.emailHint")}</span>
        </dd>
      </dl>
    </section>
  );
}

/** Light, dark or the device's own setting, remembered on this browser. */
function AppearanceSection() {
  const { t } = useI18n();
  const [theme, setThemeState] = useState<Theme>(getTheme);
  const choose = (value: Theme) => {
    setTheme(value);
    setThemeState(value);
  };
  const options: { value: Theme; label: string; icon?: "sun" | "moon" }[] = [
    { value: "system", label: t("theme.system") },
    { value: "light", label: t("theme.light"), icon: "sun" },
    { value: "dark", label: t("theme.dark"), icon: "moon" },
  ];
  return (
    <section className="card settings-section" id="settings-appearance-section" aria-labelledby="settings-appearance">
      <h2 id="settings-appearance">{t("settings.appearance")}</h2>
      <p className="hint">{t("settings.themeHint")}</p>
      <div className="theme-choices" role="radiogroup" aria-labelledby="settings-appearance">
        {options.map((option) => (
          <label key={option.value} className={theme === option.value ? "choice selected" : "choice"}>
            <input type="radio" name="theme" checked={theme === option.value} onChange={() => choose(option.value)} />
            {option.icon && <Icon name={option.icon} size={18} />}
            {option.label}
          </label>
        ))}
      </div>
    </section>
  );
}

function LanguageSection({ user }: { user: User }) {
  const { t } = useI18n();
  const save = useSaveProfile();
  const queryClient = useQueryClient();
  const choose = (language: Language) => {
    // Shown at once; the account follows (and a failure puts the previous language back).
    const previous = queryClient.getQueryData<User>(meKey);
    queryClient.setQueryData<User>(meKey, { ...user, language });
    save.mutate({ language }, { onError: () => queryClient.setQueryData(meKey, previous) });
  };
  return (
    <section className="card settings-section" id="settings-language-section" aria-labelledby="settings-language">
      <h2 id="settings-language">{t("settings.language")}</h2>
      <p className="hint">{t("settings.languageHint")}</p>
      <div className="language-grid" role="radiogroup" aria-labelledby="settings-language">
        {LANGUAGES.map((l) => (
          <label key={l.code} className={l.code === user.language ? "language-option selected" : "language-option"} lang={l.code}>
            <input
              type="radio"
              name="language"
              value={l.code}
              checked={l.code === user.language}
              disabled={save.isPending}
              onChange={() => choose(l.code)}
            />
            {l.name}
          </label>
        ))}
      </div>
      {user.language !== "en" && <p className="hint">{t("settings.translationNote")}</p>}
      <ErrorBanner error={save.error} />
    </section>
  );
}

function DailyGoalForm({ current }: { current: number }) {
  const { t } = useI18n();
  const save = useSaveProfile();
  const [goal, setGoal] = useState(String(current));
  const goalId = useId();
  const value = Number(goal);
  const valid = Number.isInteger(value) && value >= 1 && value <= 500;
  return (
    <form
      className="settings-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) save.mutate({ daily_goal: value });
      }}
    >
      <label htmlFor={goalId}>{t("settings.dailyGoal")}</label>
      <div className="inline-field">
        <input id={goalId} type="number" min={1} max={500} value={goal} onChange={(e) => setGoal(e.target.value)} />
        <button type="submit" disabled={save.isPending || !valid || value === current}>
          {t("common.save")}
        </button>
      </div>
      <p className="hint">{t("settings.dailyGoalHint")}</p>
      <ErrorBanner error={save.error} />
    </form>
  );
}

function SecuritySection() {
  const { t } = useI18n();
  const { signOut } = useAuth();
  const [changing, setChanging] = useState(false);
  return (
    <section className="card settings-section" id="settings-security-section" aria-labelledby="settings-security">
      <h2 id="settings-security">{t("settings.security")}</h2>
      {changing ? (
        <ChangePasswordForm onDone={() => setChanging(false)} />
      ) : (
        <div>
          <button type="button" onClick={() => setChanging(true)}>
            {t("password.change")}
          </button>
        </div>
      )}
      <div>
        <button type="button" className="danger" onClick={signOut}>
          {t("account.signOut")}
        </button>
        <p className="hint">{t("settings.signOutHint")}</p>
      </div>
    </section>
  );
}
