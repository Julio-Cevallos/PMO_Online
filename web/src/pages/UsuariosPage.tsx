import { useState } from 'react'
import { Plus } from 'lucide-react'
import { BotonDesbloquear, UsuarioDialog } from '@/components/usuarios/AccionesUsuario'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useUsuarios } from '@/lib/consultas'
import { mensajeDeError } from '@/lib/errores'
import { tienePermiso, useMe } from '@/lib/session'
import { nombreDeUsuario, type Usuario } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const TAMANO_PAGINA = 50

/** Administración de cuentas (quien tiene el permiso global de gestionar usuarios: Admin y superusuario). */
export function UsuariosPage() {
  const me = useMe()
  const permitido = tienePermiso(me.data, 'accounts.manage_users')
  const [pagina, setPagina] = useState(1)
  const [soloActivos, setSoloActivos] = useState(false)
  const usuarios = useUsuarios(pagina, soloActivos, permitido)
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<Usuario | null>(null)

  if (me.data && !permitido) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        No tienes acceso a esta sección.
      </p>
    )
  }

  const puedeDarAdmin = me.data?.is_superuser ?? false
  const filas = usuarios.data?.results ?? []
  const total = usuarios.data?.count ?? 0
  const paginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Usuarios</h1>
          <p className="text-sm text-muted-foreground">
            Las cuentas de la plataforma. Las cuentas no se borran: se desactivan.
          </p>
        </div>
        <Button className="shrink-0" onClick={() => setCreando(true)}>
          <Plus />
          Nueva cuenta
        </Button>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4"
          checked={soloActivos}
          onChange={(e) => {
            setSoloActivos(e.target.checked)
            setPagina(1)
          }}
        />
        Mostrar solo cuentas activas
      </label>

      {usuarios.isPending && <p className="text-muted-foreground">Cargando…</p>}

      {usuarios.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">
            {mensajeDeError(usuarios.error, 'No se pudieron cargar los usuarios.')}
          </p>
          <Button variant="outline" onClick={() => usuarios.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {usuarios.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No hay cuentas que mostrar.
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Usuarios</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Persona</th>
                <th scope="col" className="px-4 py-2 font-medium">Correo</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((u) => (
                <tr key={u.id} className={cn(!u.is_active && 'text-muted-foreground')}>
                  <td className="px-4 py-3">
                    <p className="font-medium">{nombreDeUsuario(u)}</p>
                    <p className="text-xs text-muted-foreground">{u.username}</p>
                  </td>
                  <td className="px-4 py-3">{u.email || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant={u.is_active ? 'secondary' : 'outline'}>
                        {u.is_active ? 'Activa' : 'Desactivada'}
                      </Badge>
                      {u.is_admin && <Badge>Admin</Badge>}
                      {u.is_moderator && <Badge variant="outline">Moderador</Badge>}
                      {u.is_locked && <Badge variant="destructive">Bloqueada</Badge>}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      {u.is_locked && <BotonDesbloquear usuario={u} />}
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Editar a ${u.username}`}
                        onClick={() => setEditando(u)}
                      >
                        Editar
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {paginas > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Página {pagina} de {paginas} ({total} cuentas)
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
              Anterior
            </Button>
            <Button variant="outline" size="sm" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>
              Siguiente
            </Button>
          </div>
        </div>
      )}

      <UsuarioDialog open={creando} usuario={null} puedeDarAdmin={puedeDarAdmin} onClose={() => setCreando(false)} />
      <UsuarioDialog
        open={editando !== null}
        usuario={editando}
        puedeDarAdmin={puedeDarAdmin}
        onClose={() => setEditando(null)}
      />
    </div>
  )
}
