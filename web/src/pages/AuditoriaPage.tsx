import { HistorialEventos } from '@/components/auditoria/HistorialEventos'
import { tienePermiso, useMe } from '@/lib/session'

/** Historial de auditoría de toda la plataforma (quien tiene el permiso global de verlo: Admin y superusuario). */
export function AuditoriaPage() {
  const me = useMe()

  if (me.data && !tienePermiso(me.data, 'audit.view_system_log')) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        No tienes acceso a esta sección.
      </p>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Auditoría</h1>
        <p className="text-sm text-muted-foreground">
          Quién hizo qué y cuándo. El historial solo se consulta: no se puede editar ni borrar. El de cada
          entidad también está en su pestaña «Historial».
        </p>
      </div>
      {me.data && <HistorialEventos />}
    </div>
  )
}
