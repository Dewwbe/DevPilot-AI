const MESSAGES: Record<string, string> = {
  cancelled: "Sign-in was cancelled. You can try again whenever you are ready.",
  failed: "GitHub sign-in did not complete. Please try again.",
  not_allowed: "That GitHub account is not on this deployment's allow-list.",
};

export function LoginPage() {
  const err = new URLSearchParams(window.location.search).get("login_error");
  return (
    <div className="login-wrap">
      <div className="card login-card">
        <div className="logo logo-lg"><span className="logo-mark">DP</span> DevPilot AI</div>
        <h1>Fix failing CI, faster.</h1>
        <p className="muted">
          Connect a GitHub repository and DevPilot reads the failed workflow runs, explains the root
          cause with evidence from the log, and proposes a fix. Nothing changes until you approve it.
        </p>
        {err && <div className="notice notice-error" role="alert">{MESSAGES[err] ?? MESSAGES.failed}</div>}
        <a className="btn btn-primary btn-lg" href="/api/auth/login">
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
          </svg>
          Continue with GitHub
        </a>
        <p className="muted small">
          We only read your public GitHub profile (name and avatar) to identify you as the reviewer.
          No repository access is requested.
        </p>
      </div>
    </div>
  );
}
