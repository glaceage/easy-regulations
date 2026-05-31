import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken } from "../api/client";
import { getAuthRole, getHomeRoute, isOwnerLike, isReviewer } from "../lib/auth";

export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const role = getAuthRole();
  const reviewer = isReviewer(role);
  const ownerLike = isOwnerLike(role);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await api.listNotifications();
        if (!cancelled) setUnread(items.filter((n) => !n.read).length);
      } catch {
        if (!cancelled) setUnread(0);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  function handleLogout() {
    clearToken();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to={getHomeRoute(role)}>制度修订管理平台</Link>
        <nav>
          {reviewer && <Link to="/reviews">我的评审</Link>}
          <Link to="/policies">制度库</Link>
          {ownerLike && <Link to="/admin/policies/new">新建制度</Link>}
          <Link to="/notifications">
            通知{unread > 0 ? `（${unread}）` : ""}
          </Link>
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
