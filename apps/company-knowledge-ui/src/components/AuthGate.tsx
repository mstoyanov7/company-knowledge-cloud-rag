import { ArrowRight, Building2, Layers, Lock, Mail, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { login, register, type AuthResponse } from "../api/auth";
import type { UiSettings } from "../api/admin";

const DEPARTMENTS = [
  "People & HR",
  "Finance",
  "Engineering",
  "IT & Security",
  "Product",
  "Sales",
  "Operations",
  "Legal"
];

type AuthGateProps = {
  onSignIn: (response: AuthResponse, message: string) => void;
  uiSettings: UiSettings;
};

export function AuthGate({ onSignIn, uiSettings }: AuthGateProps) {
  const [screen, setScreen] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }
    await submitLogin(() => login({ email, password }), "Welcome back.");
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") || "").trim();
    const email = String(data.get("email") || "").trim();
    const dept = String(data.get("dept") || "");
    const password = String(data.get("password") || "");
    if (!name) {
      setError("Please enter your full name.");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      const response = await register({ name, email, dept, role: "Employee", password });
      setScreen("login");
      setNotice(response.message || "Your request is pending administrator approval.");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Access request failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitLogin(action: () => Promise<AuthResponse>, message: string) {
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      onSignIn(await action(), message);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth__bg" />
      <div className="auth__panel">
        <div className="auth__brandrow">
          <span className="brand__mark" style={{ width: 34, height: 34, borderRadius: 10 }}>
            {uiSettings.logo_url ? (
              <img src={uiSettings.logo_url} alt="" />
            ) : uiSettings.logo_text ? (
              <b>{uiSettings.logo_text.slice(0, 3).toUpperCase()}</b>
            ) : (
              <Layers size={19} aria-hidden="true" />
            )}
          </span>
          <div>
            <div className="brand__name">{uiSettings.app_name}</div>
            <div className="brand__sub">{uiSettings.app_subtitle}</div>
          </div>
        </div>

        {error ? <div className="auth__err">{error}</div> : null}
        {notice ? <div className="auth__ok">{notice}</div> : null}

        {screen === "login" ? (
          <>
            <h1 className="auth__h">Sign in</h1>
            <p className="auth__sub">Welcome back. Sign in to search your company's knowledge base.</p>
            <form className="auth__form" onSubmit={handleLogin}>
              <label className="fld">
                <span className="fld__lbl">Work email</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <Mail size={16} aria-hidden="true" />
                  </span>
                  <input className="fld__in" type="email" name="email" autoComplete="username" />
                </span>
              </label>
              <label className="fld">
                <span className="fld__lbl">Password</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <Lock size={16} aria-hidden="true" />
                  </span>
                  <input
                    className="fld__in"
                    type="password"
                    name="password"
                    placeholder="At least 8 characters"
                    autoComplete="current-password"
                  />
                </span>
              </label>
              <button className="auth__submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Signing in" : "Sign in"} <ArrowRight size={15} aria-hidden="true" />
              </button>
            </form>
            <div className="auth__foot">
              Don't have access yet?{" "}
              <button className="auth__link" type="button" onClick={() => { setError(null); setNotice(null); setScreen("register"); }}>
                Request an account
              </button>
            </div>
          </>
        ) : (
          <>
            <button className="auth__back" type="button" onClick={() => { setError(null); setNotice(null); setScreen("login"); }}>
              Back to sign in
            </button>
            <h1 className="auth__h">Request access</h1>
            <p className="auth__sub">Submit your account request for administrator approval.</p>
            <form className="auth__form" onSubmit={handleRegister}>
              <label className="fld">
                <span className="fld__lbl">Full name</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <UserRound size={16} aria-hidden="true" />
                  </span>
                  <input className="fld__in" name="name" placeholder="Alex Morgan" />
                </span>
              </label>
              <label className="fld">
                <span className="fld__lbl">Work email</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <Mail size={16} aria-hidden="true" />
                  </span>
                  <input className="fld__in" type="email" name="email" placeholder="alex.morgan@example.com" />
                </span>
              </label>
              <label className="fld">
                <span className="fld__lbl">Department</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <Building2 size={16} aria-hidden="true" />
                  </span>
                  <select className="fld__in fld__sel" name="dept" defaultValue={DEPARTMENTS[0]}>
                    {DEPARTMENTS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </span>
              </label>
              <label className="fld">
                <span className="fld__lbl">Create password</span>
                <span className="fld__box">
                  <span className="fld__ico">
                    <Lock size={16} aria-hidden="true" />
                  </span>
                  <input
                    className="fld__in"
                    type="password"
                    name="password"
                    placeholder="At least 8 characters"
                    autoComplete="new-password"
                  />
                </span>
              </label>
              <button className="auth__submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Submitting request" : "Request access"} <ArrowRight size={15} aria-hidden="true" />
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

