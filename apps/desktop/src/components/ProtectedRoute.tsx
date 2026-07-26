import { Navigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const profileOpened = useAuthStore((s) => s.profileOpened);

  if (!profileOpened) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
