import { useState, type FormEvent } from "react";
import { userMessage } from "../api/client";
import { BrandLogo } from "../brand/BrandLogo";
import { LANGUAGES, useI18n, type Language } from "../i18n";
import { useAuth } from "./AuthContext";
import { ForgotPasswordForm } from "./PasswordPages";

export function SignInPage() {
  const { signIn, register } = useAuth();
  const { t, language, setLocalLanguage } = useI18n();
  const [mode, setMode] = useState<"signIn" | "register" | "forgot">("signIn");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort = mode === "register" && password.length < 12;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (tooShort) {
      setError(t("signin.passwordRule"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "signIn") await signIn(email.trim(), password);
      else await register(email.trim(), password, language);
      setPassword("");
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "forgot") {
    return (
      <main className="signin">
        <ForgotPasswordForm onBack={() => setMode("signIn")} />
      </main>
    );
  }

  return (
    <main className="signin">
      <form className="card signin-card" onSubmit={submit} aria-labelledby="signin-title">
        <a href="/" className="signin-logo" aria-label={t("nav.home")}>
          <BrandLogo height={36} />
        </a>
        <h1 id="signin-title">{mode === "signIn" ? t("signin.title") : t("signin.registerTitle")}</h1>
        <label>
          {t("signin.email")}
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          {t("signin.password")}
          <input
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === "register" && <p className="hint">{t("signin.passwordRule")}</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy || !email || !password}>
          {busy ? t("common.pleaseWait") : mode === "signIn" ? t("signin.submit") : t("signin.register")}
        </button>
        {mode === "signIn" && (
          <button type="button" className="link" onClick={() => setMode("forgot")}>
            {t("signin.forgot")}
          </button>
        )}
        <button type="button" className="link" onClick={() => setMode(mode === "signIn" ? "register" : "signIn")}>
          {mode === "signIn" ? t("signin.toRegister") : t("signin.toSignIn")}
        </button>
        <label className="language-picker">
          {t("signin.language")}
          <select value={language} onChange={(e) => setLocalLanguage(e.target.value as Language)}>
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} lang={l.code}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
      </form>
    </main>
  );
}
