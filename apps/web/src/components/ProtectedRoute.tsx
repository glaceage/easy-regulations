import { Navigate, Outlet } from "react-router-dom";
import { isAuthenticated } from "../api/client";

export function ProtectedRoute() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
