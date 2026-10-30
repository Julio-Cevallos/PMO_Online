import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import { EntidadDetallePage } from '@/pages/EntidadDetallePage'
import { AuditoriaPage } from '@/pages/AuditoriaPage'
import { EntidadesPage } from '@/pages/EntidadesPage'
import { InvitacionesPage } from '@/pages/InvitacionesPage'
import { PortafolioDetallePage } from '@/pages/PortafolioDetallePage'
import { PortafoliosPage } from '@/pages/PortafoliosPage'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { TiposEntidadPage } from '@/pages/TiposEntidadPage'
import { UsuariosPage } from '@/pages/UsuariosPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Pantallas con sesión: comparten el menú lateral (AppLayout). */}
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/entities" replace />} />
        <Route path="entities" element={<EntidadesPage />} />
        <Route path="entities/:id" element={<EntidadDetallePage />} />
        <Route path="entity-types" element={<TiposEntidadPage />} />
        <Route path="invitations" element={<InvitacionesPage />} />
        <Route path="portfolios" element={<PortafoliosPage />} />
        <Route path="portfolios/:id" element={<PortafolioDetallePage />} />
        <Route path="users" element={<UsuariosPage />} />
        <Route path="audit" element={<AuditoriaPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
