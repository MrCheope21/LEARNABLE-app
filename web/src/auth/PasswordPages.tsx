import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { tokenStore, userMessage } from "../api/client";
import { auth } from "../api/endpoints";
import { BrandLogo } from "../brand/BrandLogo";

const MIN_LENGTH = 12;

/** "Forgot your password?": the same answer whether or not the email has an account. */
export function ForgotPasswordForm({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const answer = await auth.requestPasswordReset(email.trim());
      setSent(answer.detail);
    } catch (e) {
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card signin-card" onSubmit={submit} aria-labelledby="forgot-title">
      <h1 id="forgot-title">Reset your password</h1>
      {sent ? (
        <p role="status">{sent}</p>
      ) : (
        <>
          <p className="hint">Enter your account's email. We'll send a link to choose a new password; it works once, for 30 minutes.</p>
          <label>
            Email
            <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy || !email.trim()}>
            {busy ? "Please wait…" : "Send reset link"}
          </button>
        </>
      )}
      <button type="button" className="link" onClick={onBack}>
        Back to sign in
      </button>
    </form>
  );
}

/** The page a reset link opens (/reset-password?token=…), signed in or not. */
export function ResetPasswordPage() {
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
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <form className="card signin-card" onSubmit={submit} aria-labelledby="reset-title">
        <a href="/" className="signin-logo" aria-label="LEARNABLE home">
          <BrandLogo height={36} />
        </a>
        <h1 id="reset-title">Choose a new password</h1>
        {!token ? (
          <p role="alert" className="error">
            This link is incomplete. Open the link from the email again, or ask for a new one.
          </p>
        ) : done ? (
          <>
            <p role="status">Your password has been changed. Every device was signed out: sign in with the new password.</p>
            <a className="button primary" href="/">
              Sign in
            </a>
          </>
        ) : (
          <>
            <label>
              New password
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
              Repeat the new password
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                aria-invalid={mismatch}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
            <p className="hint">At least {MIN_LENGTH} characters.</p>
            {tooShort && <p className="error">Use at least {MIN_LENGTH} characters.</p>}
            {mismatch && <p className="error">The two passwords don't match.</p>}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button type="submit" className="primary" disabled={busy || password.length < MIN_LENGTH || password !== confirm}>
              {busy ? "Please wait…" : "Set new password"}
            </button>
          </>
        )}
        {!done && <Link to="/">Back to sign in</Link>}
      </form>
    </main>
  );
}

/** Account menu: change the password (needs the current one). Other devices are signed out. */
export function ChangePasswordForm({ onDone }: { onDone: () => void }) {
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
      setError(userMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (changed) {
    return (
      <div role="status" className="password-changed">
        <p>Password changed. Your other devices were signed out.</p>
        <button type="button" className="link" onClick={onDone}>
          Close
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="password-form" aria-label="Change password">
      <label>
        Current password
        <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label>
        New password (12+ characters)
        <input type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="actions" style={{ marginTop: 0 }}>
        <button type="submit" className="primary" disabled={busy || !current || next.length < MIN_LENGTH}>
          Change password
        </button>
        <button type="button" className="link" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}
