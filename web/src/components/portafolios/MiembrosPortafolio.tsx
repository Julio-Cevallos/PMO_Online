import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import { useMe } from '@/lib/session'
import { nombreDeUsuario, type Portafolio, type PortafolioMiembro, type RolAsignable } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const fecha = (iso: string) => new Date(iso).toLocaleDateString('es-EC', { dateStyle: 'medium' })

function useMiembros(portafolioId: number, incluirInactivos: boolean) {
  return useQuery({
    queryKey: ['portfolio-members', portafolioId, incluirInactivos],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolios/{portafolio_id}/members/', {
        params: {
          path: { portafolio_id: portafolioId },
          query: incluirInactivos ? { activa: 'todas' } : {},
        },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

function InvitarDialog({
  portafolioId,
  roles,
  open,
  onClose,
  onHecho,
}: {
  portafolioId: number
  roles: RolAsignable[]
  open: boolean
  onClose: () => void
  onHecho: (texto: string) => void
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Invitar al portafolio"
      description="La persona decide si acepta. Hasta entonces no tiene acceso al portafolio."
    >
      {/* `key` reinicia el formulario cada vez que se abre. */}
      {open && <FormularioInvitar portafolioId={portafolioId} roles={roles} onClose={onClose} onHecho={onHecho} />}
    </Dialog>
  )
}

function FormularioInvitar({
  portafolioId,
  roles,
  onClose,
  onHecho,
}: {
  portafolioId: number
  roles: RolAsignable[]
  onClose: () => void
  onHecho: (texto: string) => void
}) {
  const [username, setUsername] = useState('')
  const [rol, setRol] = useState('')
  const [error, setError] = useState<string | null>(null)

  const invitar = useMutation({
    mutationFn: async () => {
      const { data, error: cuerpo, response } = await api.POST('/api/portfolios/{portafolio_id}/invitations/', {
        params: { path: { portafolio_id: portafolioId } },
        body: { username: username.trim(), rol: Number(rol) },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
      return data
    },
    onSuccess: (inv) =>
      onHecho(`Se invitó a @${inv.username} como ${inv.rol_nombre}. Entrará cuando acepte la invitación.`),
    onError: (e) => {
      if (e instanceof ErrorDeApi && e.info.status === 404) {
        setError('No existe ninguna cuenta con ese nombre de usuario.')
      } else {
        setError(mensajeDeError(e, 'No se pudo enviar la invitación.'))
      }
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (!username.trim()) return setError('Indica el nombre de usuario.')
        if (!rol) return setError('Elige un rol.')
        setError(null)
        invitar.mutate()
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="inv-pf-usuario">Nombre de usuario</Label>
        <Input
          id="inv-pf-usuario"
          autoComplete="off"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="inv-pf-rol">Rol en el portafolio</Label>
        <Select id="inv-pf-rol" className="w-full" value={rol} onChange={(e) => setRol(e.target.value)}>
          <option value="">Elige un rol</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button type="submit" disabled={invitar.isPending}>
          {invitar.isPending ? 'Invitando…' : 'Invitar'}
        </Button>
      </div>
    </form>
  )
}

function CambiarRolDialog({
  portafolioId,
  miembro,
  roles,
  onClose,
  onHecho,
}: {
  portafolioId: number
  miembro: PortafolioMiembro | null
  roles: RolAsignable[]
  onClose: () => void
  onHecho: (texto: string) => void
}) {
  const [rol, setRol] = useState('')
  const [error, setError] = useState<string | null>(null)
  const elegido = rol || String(miembro?.rol ?? '')

  const guardar = useMutation({
    mutationFn: async () => {
      const { data, error: cuerpo, response } = await api.PATCH('/api/portfolios/{portafolio_id}/members/{id}/', {
        params: { path: { portafolio_id: portafolioId, id: miembro!.id } },
        body: { rol: Number(elegido) },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
      return data
    },
    onSuccess: (m) => {
      setRol('')
      onHecho(`${nombreDeUsuario(m)} ahora es ${m.rol_nombre}.`)
    },
    onError: (e) => setError(mensajeDeError(e, 'No se pudo cambiar el rol.')),
  })

  return (
    <Dialog
      open={miembro !== null}
      onClose={() => {
        setRol('')
        setError(null)
        onClose()
      }}
      title="Cambiar el rol"
      description={miembro ? `Persona: ${nombreDeUsuario(miembro)} (@${miembro.username})` : undefined}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          guardar.mutate()
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="pf-cambiar-rol">Rol</Label>
          <Select id="pf-cambiar-rol" className="w-full" value={elegido} onChange={(e) => setRol(e.target.value)}>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardar.isPending}>
            {guardar.isPending ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}

/** Miembros e invitaciones de un portafolio. Las acciones solo aparecen a quien puede gestionarlos. */
export function MiembrosPortafolio({ portafolio }: { portafolio: Portafolio }) {
  const me = useMe()
  const queryClient = useQueryClient()
  const [incluirInactivos, setIncluirInactivos] = useState(false)
  const [aviso, setAviso] = useState<{ tipo: 'ok' | 'error'; texto: string } | null>(null)
  const [invitando, setInvitando] = useState(false)
  const [cambiando, setCambiando] = useState<PortafolioMiembro | null>(null)
  const gestiona = portafolio.puede_gestionar_miembros

  const miembros = useMiembros(portafolio.id, incluirInactivos)
  const roles = useQuery({
    queryKey: ['portfolio-assignable-roles', portafolio.id],
    enabled: gestiona,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolios/{portafolio_id}/assignable-roles/', {
        params: { path: { portafolio_id: portafolio.id } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
  const invitaciones = useQuery({
    queryKey: ['portfolio-invitations', portafolio.id],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolios/{portafolio_id}/invitations/', {
        params: { path: { portafolio_id: portafolio.id } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })

  const refrescar = () =>
    Promise.all(
      ['portfolio-members', 'portfolio-invitations', 'portfolio-assignable-roles'].map((clave) =>
        queryClient.invalidateQueries({ queryKey: [clave, portafolio.id] }),
      ),
    )

  const modificar = useMutation({
    mutationFn: async ({ m, activa }: { m: PortafolioMiembro; activa: boolean }) => {
      const { data, error, response } = await api.PATCH('/api/portfolios/{portafolio_id}/members/{id}/', {
        params: { path: { portafolio_id: portafolio.id, id: m.id } },
        body: { activa },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return { m, activa }
    },
    onSuccess: ({ m, activa }) => {
      setAviso({ tipo: 'ok', texto: `${nombreDeUsuario(m)} ${activa ? 'se reactivó' : 'se desactivó'}.` })
      void refrescar()
    },
    onError: (e) => setAviso({ tipo: 'error', texto: mensajeDeError(e, 'No se pudo hacer el cambio.') }),
  })

  const cancelar = useMutation({
    mutationFn: async (id: number) => {
      const { error, response } = await api.DELETE('/api/portfolios/{portafolio_id}/invitations/{id}/', {
        params: { path: { portafolio_id: portafolio.id, id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, error))
    },
    onSuccess: () => void refrescar(),
    onError: (e) => setAviso({ tipo: 'error', texto: mensajeDeError(e, 'No se pudo cancelar la invitación.') }),
  })

  const asignables = new Set((roles.data ?? []).map((r) => r.id))
  const puedeGestionar = (m: PortafolioMiembro) =>
    gestiona && asignables.has(m.rol) && m.usuario !== me.data?.id
  const filas = miembros.data ?? []
  const pendientes = invitaciones.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4"
            checked={incluirInactivos}
            onChange={(e) => setIncluirInactivos(e.target.checked)}
          />
          Mostrar también los inactivos
        </label>
        {gestiona && (
          <Button onClick={() => setInvitando(true)}>
            <UserPlus />
            Invitar al portafolio
          </Button>
        )}
      </div>

      {aviso && (
        <p
          role={aviso.tipo === 'error' ? 'alert' : 'status'}
          className={cn('text-sm', aviso.tipo === 'error' ? 'text-destructive' : 'text-muted-foreground')}
        >
          {aviso.texto}
        </p>
      )}

      {miembros.isPending && <p className="text-muted-foreground">Cargando…</p>}
      {miembros.isError && (
        <p role="alert" className="text-destructive">
          {mensajeDeError(miembros.error, 'No se pudieron cargar los miembros.')}
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Miembros de {portafolio.nombre}</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Persona</th>
                <th scope="col" className="px-4 py-2 font-medium">Rol</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
                {gestiona && <th scope="col" className="px-4 py-2 text-right font-medium">Acciones</th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((m) => (
                <tr key={m.id} className={cn(!m.activa && 'text-muted-foreground')}>
                  <td className="px-4 py-3">
                    <p className="font-medium">{nombreDeUsuario(m)}</p>
                    <p className="text-xs text-muted-foreground">@{m.username}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{m.rol_nombre}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={m.activa ? 'secondary' : 'outline'}>{m.activa ? 'Activo' : 'Inactivo'}</Badge>
                  </td>
                  {gestiona && (
                    <td className="px-4 py-3">
                      {puedeGestionar(m) && (
                        <div className="flex justify-end gap-2">
                          {m.activa ? (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                aria-label={`Cambiar el rol de ${nombreDeUsuario(m)}`}
                                onClick={() => setCambiando(m)}
                              >
                                Cambiar rol
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                aria-label={`Desactivar a ${nombreDeUsuario(m)}`}
                                disabled={modificar.isPending}
                                onClick={() => {
                                  setAviso(null)
                                  modificar.mutate({ m, activa: false })
                                }}
                              >
                                Desactivar
                              </Button>
                            </>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              aria-label={`Reactivar a ${nombreDeUsuario(m)}`}
                              disabled={modificar.isPending}
                              onClick={() => {
                                setAviso(null)
                                modificar.mutate({ m, activa: true })
                              }}
                            >
                              Reactivar
                            </Button>
                          )}
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pendientes.length > 0 && (
        <section aria-labelledby="titulo-inv-pf" className="space-y-2">
          <h2 id="titulo-inv-pf" className="text-sm font-medium">
            Invitaciones pendientes ({pendientes.length})
          </h2>
          <ul className="divide-y rounded-xl ring-1 ring-foreground/10">
            {pendientes.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">
                    {nombreDeUsuario(i)} <span className="font-normal text-muted-foreground">@{i.username}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Invitó {i.invitado_por_nombre || 'alguien'} el {fecha(i.creado_en)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{i.rol_nombre}</Badge>
                  {gestiona && asignables.has(i.rol) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Cancelar la invitación a ${i.username}`}
                      disabled={cancelar.isPending}
                      onClick={() => {
                        setAviso(null)
                        cancelar.mutate(i.id)
                      }}
                    >
                      Cancelar
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <InvitarDialog
        portafolioId={portafolio.id}
        roles={roles.data ?? []}
        open={invitando}
        onClose={() => setInvitando(false)}
        onHecho={(texto) => {
          setInvitando(false)
          setAviso({ tipo: 'ok', texto })
          void refrescar()
        }}
      />
      <CambiarRolDialog
        portafolioId={portafolio.id}
        miembro={cambiando}
        roles={roles.data ?? []}
        onClose={() => setCambiando(null)}
        onHecho={(texto) => {
          setCambiando(null)
          setAviso({ tipo: 'ok', texto })
          void refrescar()
        }}
      />
    </div>
  )
}
