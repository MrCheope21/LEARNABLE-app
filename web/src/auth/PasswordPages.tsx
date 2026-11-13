import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { tokenStore, userMessage } from "../api/client";
import { auth } from "../api/endpoints";
import { BrandLogo } from "../brand/BrandLogo";
import { useI18n } from "../i18n";

const MIN_LENGTH = 12;

/** "Forgot your password?": the same answer whether or not the email has an account. */
export function ForgotPasswordForm({ onBack }: { onBack: () => void }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.requestPasswordReset(email.trim());
      // The same wording whether or not the email has an account (the server's is English).
      setSent(t("reset.sentMessage"));
    } catch (e) {
      setError(userMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card signin-card" onSubmit={submit} aria-labelledby="forgot-title">
      <h1 id="forgot-title">{t("reset.title")}</h1>
      {sent ? (
        <p role="status">{sent}</p>
      ) : (
        <>
          <p className="hint">{t("reset.intro")}</p>
          <label>
            {t("signin.email")}
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy || !email.trim()}>
            {busy ? t("common.pleaseWait") : t("reset.send")}
          </button>
        </>
      )}
      <button type="button" className="link" onClick={onBack}>
        {t("reset.back")}
      </button>
    </form>
  );
}

/** The page a reset link opens (/reset-password?token=…), signed in or not. */
export function ResetPasswordPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mismatch = confirm.length > 0 && password !== confirm;
  const tooShort = password.length > 0 && password.length < MIN_LENGTH;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < MIN_LENGTH || password !== confirm) return;
    setBusy(true);
    setError(null);
    try {
      await auth.confirmPasswordReset(token, password);
      // Every session of the account ended on the server; this browser's too.
      tokenStore.clear();
      setDone(true);
    } catch (e) {
      setError(userMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <form className="card signin-card" onSubmit={submit} aria-labelledby="reset-title">
        <a href="/" className="signin-logo" aria-label={t("nav.home")}>
          <BrandLogo height={36} />
        </a>
        <h1 id="reset-title">{t("reset.chooseTitle")}</h1>
        {!token ? (
          <p role="alert" className="error">
            {t("reset.incomplete")}
          </p>
        ) : done ? (
          <>
            <p role="status">{t("reset.done")}</p>
            <a className="button primary" href="/">
              {t("signin.submit")}
            </a>
          </>
        ) : (
          <>
            <label>
              {t("reset.newPassword")}
              <input
                type="password"
                autoComplete="new-password"
                required
                value={password}
                aria-invalid={tooShort}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              {t("reset.repeat")}
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                aria-invalid={mismatch}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
            <p className="hint">{t("signin.passwordRule")}</p>
            {tooShort && <p className="error">{t("reset.tooShort", { n: MIN_LENGTH })}</p>}
            {mismatch && <p className="error">{t("reset.mismatch")}</p>}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button type="submit" className="primary" disabled={busy || password.length < MIN_LENGTH || password !== confirm}>
              {busy ? t("common.pleaseWait") : t("reset.set")}
            </button>
          </>
        )}
        {!done && <Link to="/">{t("reset.back")}</Link>}
      </form>
    </main>
  );
}

/** Account menu: change the password (needs the current one). Other devices are signed out. */
export function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [changed, setChanged] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next.length < MIN_LENGTH) return;
    setBusy(true);
    setError(null);
    try {
      const token = await auth.changePassword(current, next);
      // The old token stopped working: keep this browser signed in with the new one.
      tokenStore.set(token.access_token);
      setChanged(true);
      setCurrent("");
      setNext("");
    } catch (e) {
      setError(userMessage(e, t));
    } finally {
      setBusy(false);
    }
  }

  if (changed) {
    return (
      <div role="status" className="password-changed">
        <p>{t("password.changed")}</p>
        <button type="button" className="link" onClick={onDone}>
          {t("common.close")}
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="password-form" aria-label={t("password.change")}>
      <label>
        {t("password.current")}
        <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label>
        {t("password.new")}
        <input type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={busy || !current || next.length < MIN_LENGTH}>
          {t("password.change")}
        </button>
        <button type="button" className="link" onClick={onDone}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}
