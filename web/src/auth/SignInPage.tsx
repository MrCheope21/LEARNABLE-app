import { useState, type FormEvent } from "react";
import { userMessage } from "../api/client";
import { BrandLogo } from "../brand/BrandLogo";
import { useAuth } from "./AuthContext";
import { ForgotPasswordForm } from "./PasswordPages";

export function SignInPage() {
  const { signIn, register } = useAuth();
  const [mode, setMode] = useState<"signIn" | "register" | "forgot">("signIn");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort = mode === "register" && password.length < 12;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (tooShort) {
      setError("Use at least 12 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "signIn") await signIn(email.trim(), password);
      else await register(email.trim(), password);
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
        <a href="/" className="signin-logo" aria-label="LEARNABLE home">
          <BrandLogo height={36} />
        </a>
        <h1 id="signin-title">{mode === "signIn" ? "Sign in to LEARNABLE" : "Create your account"}</h1>
        <label>
          Email
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {mode === "register" && <p className="hint">At least 12 characters.</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy || !email || !password}>
          {busy ? "Please wait…" : mode === "signIn" ? "Sign in" : "Create account"}
        </button>
        {mode === "signIn" && (
          <button type="button" className="link" onClick={() => setMode("forgot")}>
            Forgot your password?
          </button>
        )}
        <button type="button" className="link" onClick={() => setMode(mode === "signIn" ? "register" : "signIn")}>
          {mode === "signIn" ? "Create an account" : "I already have an account"}
        </button>
      </form>
    </main>
  );
}
