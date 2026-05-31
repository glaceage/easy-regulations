import { getToken } from "../api/client";

export type UserRole = "owner" | "reviewer" | "policy_admin" | "reader" | "sys_admin";

export function getAuthRole(): UserRole | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? "")) as { role?: string };
    const role = payload.role;
    if (
      role === "owner" ||
      role === "reviewer" ||
      role === "policy_admin" ||
      role === "reader" ||
      role === "sys_admin"
    ) {
      return role;
    }
    return null;
  } catch {
    return null;
  }
}

export function isOwnerLike(role: UserRole | null): boolean {
  return role === "owner" || role === "policy_admin" || role === "sys_admin";
}

export function isReviewer(role: UserRole | null): boolean {
  return role === "reviewer";
}

export function isPolicyAdmin(role: UserRole | null): boolean {
  return role === "policy_admin";
}
