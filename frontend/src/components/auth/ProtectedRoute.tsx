import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LineChart } from "lucide-react";
import { useAuth } from "@/lib/auth";

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.loading) {
    return (
      <main className="grid min-h-screen place-items-center" aria-busy="true" aria-label="正在验证登录状态">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <LineChart className="h-5 w-5 animate-pulse text-primary" />
          正在进入投研工作台…
        </div>
      </main>
    );
  }

  if (auth.enabled && !auth.authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
