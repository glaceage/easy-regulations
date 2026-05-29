import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { PolicyDetailPage } from "./pages/PolicyDetailPage";
import { RevisionWorkspacePage } from "./pages/RevisionWorkspacePage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/policies" element={<PoliciesPage />} />
            <Route path="/policies/:id" element={<PolicyDetailPage />} />
            <Route path="/revisions/:id" element={<RevisionWorkspacePage />} />
          </Route>
        </Route>
        <Route path="/" element={<Navigate to="/policies" replace />} />
        <Route path="*" element={<Navigate to="/policies" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
