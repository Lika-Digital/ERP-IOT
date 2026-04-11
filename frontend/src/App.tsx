import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/auth/ProtectedRoute'
import Layout from './components/layout/Layout'
import Login from './pages/Login'
import MarinaSelect from './pages/MarinaSelect'
import Dashboard from './pages/Dashboard'
import PedestalControl from './pages/PedestalControl'
import Energy from './pages/Energy'
import Alarms from './pages/Alarms'
import Berths from './pages/Berths'
import PedestalDetail from './pages/PedestalDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          {/* Default: redirect to marina select */}
          <Route index element={<Navigate to="/marinas" replace />} />

          <Route path="marinas" element={<MarinaSelect />} />

          <Route path="marinas/:marinaId">
            <Route index element={<Navigate to="dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="pedestals/:pedestalId" element={<PedestalDetail />} />
            <Route path="control" element={<PedestalControl />} />
            <Route path="energy" element={<Energy />} />
            <Route path="alarms" element={<Alarms />} />
            <Route path="berths" element={<Berths />} />
          </Route>
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
