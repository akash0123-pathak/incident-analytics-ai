import { useState } from "react";
import { IconShield, IconAlertTriangle } from "./Icons.jsx";

export default function LoginGate({ onAuthenticate, loading, error }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState(null);

  const emailError = email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? "Enter a valid email address." : null;
  const passwordError = password && !/(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}/.test(password)
    ? "Use 8+ characters with uppercase, lowercase, number, and special character."
    : null;
  const confirmError = mode === "register" && confirmPassword && password !== confirmPassword ? "Passwords do not match." : null;
  const hasValidationError = Boolean(emailError || passwordError || confirmError);

  const submit = (event) => {
    event.preventDefault();
    setFormError(null);
    if (hasValidationError || !email || !password || (mode === "register" && !confirmPassword)) {
      setFormError("Please fix the highlighted fields.");
      return;
    }
    onAuthenticate({ mode, email, password });
  };

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setFormError(null);
    setPassword("");
    setConfirmPassword("");
  };

  return (
    <main className="login-page">
      <div className="login-container">
        <section className="login-card">
          <div className="login-header">
            <div className="login-mark">
              <IconShield size={24} />
            </div>
            <span className="eyebrow">SIGNALDECK / SECURE WORKSPACE</span>
            <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
            <p>
              {mode === "login" ? "Sign in to access the incident intelligence platform." : "Register once to access the incident intelligence platform."}
            </p>
          </div>

          <form onSubmit={submit} className="login-form">
            <div className="form-group">
              <label className="field-label" htmlFor="account-email">Email address</label>
              <input id="account-email" className={`text-input ${emailError ? "text-input--error" : ""}`} type="email" value={email} onChange={(e) => { setEmail(e.target.value); setFormError(null); }} placeholder="you@company.com" autoComplete="email" required aria-invalid={Boolean(emailError)} />
              {emailError && <span className="field-error">{emailError}</span>}
            </div>
            <div className="form-group">
              <label className="field-label" htmlFor="account-password">Password</label>
              <input id="account-password" className={`text-input ${passwordError ? "text-input--error" : ""}`} type="password" value={password} onChange={(e) => { setPassword(e.target.value); setFormError(null); }} placeholder="8+ chars, upper/lower, number, symbol" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} required aria-invalid={Boolean(passwordError)} />
              {passwordError && <span className="field-error">{passwordError}</span>}
            </div>
            {mode === "register" && <div className="form-group">
              <label className="field-label" htmlFor="account-confirm-password">Confirm password</label>
              <input id="account-confirm-password" className={`text-input ${confirmError ? "text-input--error" : ""}`} type="password" value={confirmPassword} onChange={(e) => { setConfirmPassword(e.target.value); setFormError(null); }} placeholder="Re-enter your password" autoComplete="new-password" minLength={8} required aria-invalid={Boolean(confirmError)} />
              {confirmError && <span className="field-error">{confirmError}</span>}
            </div>}

            {(error || formError) && (
              <div className="login-error">
                <IconAlertTriangle size={16} />
                <span>{formError || error}</span>
              </div>
            )}

            <button
              type="submit"
              className="btn btn--primary btn--block btn--lg"
              disabled={loading}
            >
              {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <div className="auth-switch">
            <span>{mode === "login" ? "New to SignalDeck?" : "Already have an account?"}</span>
            <button type="button" className="btn-link" onClick={() => switchMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Register" : "Sign in"}
            </button>
          </div>

        </section>
      </div>
    </main>
  );
}
