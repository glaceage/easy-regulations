import { FormEvent, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, isAuthenticated, setToken } from "../api/client";

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionExpired = searchParams.get("expired") === "1";
  const returnTo = searchParams.get("from") || "/policies";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (isAuthenticated()) {
    return <Navigate to="/policies" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { access_token } = await api.login(username, password);
      setToken(access_token);
      navigate(returnTo.startsWith("/") ? returnTo : "/policies");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="card login-card">
        <h1>制度修订管理平台</h1>
        <p className="subtitle">请使用企业账号登录</p>
        {sessionExpired && (
          <div className="info-banner">登录已过期或数据已重置，请重新登录。</div>
        )}
        {error && <div className="error-banner">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={loading}>
            {loading ? "登录中…" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
