import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

interface ProtectedRouteProps {
  children: React.ReactNode
  superAdminOnly?: boolean
}

export default function ProtectedRoute({
  children,
  superAdminOnly = false,
}: ProtectedRouteProps) {
  const { isAuthenticated, role } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (superAdminOnly && role !== 'super_admin') {
    return <Navigate to="/marinas" replace />
  }

  return <>{children}</>
}
