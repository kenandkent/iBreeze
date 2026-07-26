import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { useAppStore } from '../stores/appStore';

export function OriginGuard({ children }: { children: React.ReactNode }) {
  const backendOrigin = useAuthStore((s) => s.backendOrigin);
  if (!backendOrigin) {
    return <Navigate to="/auth/server" replace />;
  }
  return <>{children}</>;
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const profileOpened = useAuthStore((s) => s.profileOpened);
  const location = useLocation();

  if (!profileOpened) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}

export function CompanyGuard({ children }: { children: React.ReactNode }) {
  const selectedCompanyId = useAppStore((s) => s.selectedCompanyId);
  if (!selectedCompanyId) {
    return <Navigate to="/companies" replace />;
  }
  return <>{children}</>;
}
