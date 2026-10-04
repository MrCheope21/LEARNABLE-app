import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import type { Schemas } from "../../api/client";
import { auth } from "../../api/endpoints";
import { dashboardKey, meKey, TimezoneForm } from "../../app/AppShell";
import { useAuth } from "../../auth/AuthContext";
import { ChangePasswordForm } from "../../auth/PasswordPages";
import { ErrorBanner, QueryState } from "../../components/QueryState";
import { LANGUAGES, useI18n, type Language } from "../../i18n";

type User = Schemas["UserRead"];

/** Profile, interface language, study preferences and security, saved to the account. */
export function SettingsPage() {
  const { t } = useI18n();
  const me = useQuery({ queryKey: meKey, queryFn: auth.me });
  return (
    <div className="page settings-page">
      <header className="page-header">
        <h1>{t("settings.title")}</h1>
        <p className="hint">{t("settings.intro")}</p>
      </header>
      <QueryState query={me}>
        {(user) => (
          <>
            <ProfileSection user={user} />
            <LanguageSection user={user} />
            <section className="card settings-section" aria-labelledby="settings-study">
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

function ProfileSection({ user }: { user: User }) {
  const { t } = useI18n();
  const save = useSaveProfile();
  const [name, setName] = useState(user.display_name ?? "");
  const nameId = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({ display_name: name });
  };
  const initial = (user.display_name || user.email)[0]?.toUpperCase();
  return (
    <section className="card settings-section" aria-labelledby="settings-profile">
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
        <div className="inline-field">
          <input id={nameId} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          <button type="submit" disabled={save.isPending || name === (user.display_name ?? "")}>
            {save.isPending ? t("common.saving") : t("common.save")}
          </button>
        </div>
        <p className="hint">{t("settings.displayNameHint")}</p>
        {save.isSuccess && <p role="status" className="hint">{t("common.saved")}</p>}
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
    <section className="card settings-section" aria-labelledby="settings-language">
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
    <section className="card settings-section" aria-labelledby="settings-security">
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
