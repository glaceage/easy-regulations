import { Navigate, Outlet } from "react-router-dom";
import { isAuthenticated } from "../api/client";
import { getAuthRole, getHomeRoute, type UserRole } from "../lib/auth";

export function ProtectedRoute({ roles }: { roles?: UserRole[] }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  if (roles && roles.length > 0) {
    const role = getAuthRole();
    if (!role || !roles.includes(role)) {
      return <Navigate to={getHomeRoute(role)} replace />;
    }
  }
  return <Outlet />;
}
