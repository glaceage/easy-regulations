import { Link, Outlet, useNavigate } from "react-router-dom";
import { clearToken } from "../api/client";

export function Layout() {
  const navigate = useNavigate();

  function handleLogout() {
    clearToken();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/policies">制度修订管理平台</Link>
        <nav>
          <Link to="/policies">制度库</Link>
          <button type="button" className="btn btn-secondary" onClick={handleLogout} style={{ color: "#1a2332" }}>
            退出登录
          </button>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
