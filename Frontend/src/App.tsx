import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AccountPage } from "./features/settings/AccountPage";
import { AnomalyLogPage } from "./features/settings/AnomalyLogPage";
import { AuthGuard } from "./features/auth/AuthGuard";
import { CashbackPage } from "./features/cashback/CashbackPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { EmailPage } from "./features/settings/EmailPage";
import { InsightsPage } from "./features/insights/InsightsPage";
import { LandingPage } from "./features/landing/LandingPage";
import { LoginPage } from "./features/auth/LoginPage";
import { NotificationsPage } from "./features/settings/NotificationsPage";
import { SecurityPage } from "./features/settings/SecurityPage";
import { SettingsLayout } from "./features/settings/SettingsLayout";
import { SignupPage } from "./features/auth/SignupPage";
import { UsagePage } from "./features/usage/UsagePage";
import { AppShell } from "./layouts/AppShell";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/auth/login" element={<LoginPage />} />
          <Route path="/auth/signup" element={<SignupPage />} />
          <Route element={<AuthGuard />}>
            <Route element={<AppShell />}>
              <Route path="/home" element={<DashboardPage />} />
              <Route path="/usage" element={<UsagePage />} />
              <Route path="/cashback" element={<CashbackPage />} />
              <Route path="/settings" element={<SettingsLayout />}>
                <Route index element={<AccountPage />} />
                <Route path="account" element={<AccountPage />} />
                <Route path="notifications" element={<NotificationsPage />} />
                <Route path="security" element={<SecurityPage />} />
                <Route path="anomaly-log" element={<AnomalyLogPage />} />
                <Route path="email" element={<EmailPage />} />
              </Route>
              <Route path="/insights" element={<InsightsPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
