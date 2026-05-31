import { Navigate } from "react-router-dom";
import { getAuthRole, getHomeRoute } from "../lib/auth";

export function HomeRedirect() {
  return <Navigate to={getHomeRoute(getAuthRole())} replace />;
}
