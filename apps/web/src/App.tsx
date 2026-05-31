import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ConsultationPage } from "./pages/ConsultationPage";
import { CreatePolicyPage } from "./pages/CreatePolicyPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { PolicyDetailPage } from "./pages/PolicyDetailPage";
import { PublishPage } from "./pages/PublishPage";
import { ReviewInboxPage } from "./pages/ReviewInboxPage";
import { RevisionViewPage } from "./pages/RevisionViewPage";
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
            <Route path="/revisions/:id/consultation" element={<ConsultationPage />} />
            <Route path="/revisions/:id/publish" element={<PublishPage />} />
            <Route path="/revisions/:id/view" element={<RevisionViewPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route element={<ProtectedRoute roles={["reviewer"]} />}>
              <Route path="/reviews" element={<ReviewInboxPage />} />
            </Route>
            <Route element={<ProtectedRoute roles={["owner", "policy_admin", "sys_admin"]} />}>
              <Route path="/admin/policies/new" element={<CreatePolicyPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="*" element={<HomeRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}
