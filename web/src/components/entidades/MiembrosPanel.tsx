import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus } from 'lucide-react'
import { AccionesMiembroDialogs } from '@/components/entidades/AccionesMiembroDialogs'
import { InvitacionesPendientes } from '@/components/entidades/InvitacionesPendientes'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import { useMe } from '@/lib/session'
import { nombreDe, type Entidad, type Miembro } from '@/lib/tipos'
import { cn } from '@/lib/utils'

interface Aviso {
  tipo: 'ok' | 'error'
  texto: string
}

/** Miembros de una entidad. Las acciones solo aparecen donde el rol y el nivel de quien consulta lo permiten. */
export function MiembrosPanel({ entidad }: { entidad: Entidad }) {
  const me = useMe()
  const queryClient = useQueryClient()
  const [incluirInactivos, setIncluirInactivos] = useState(false)
  const [aviso, setAviso] = useState<Aviso | null>(null)
  const [agregando, setAgregando] = useState(false)
  const [cambiando, setCambiando] = useState<Miembro | null>(null)
  const [desactivando, setDesactivando] = useState<Miembro | null>(null)

  const archivada = entidad.estado === 'archivada'
  const gestiona = entidad.puede_gestionar_miembros && !archivada

  const miembros = useQuery({
    queryKey: ['members', entidad.id, incluirInactivos],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/entities/{entidad_id}/members/', {
        params: {
          path: { entidad_id: entidad.id },
          query: incluirInactivos ? { activa: 'todas' } : {},
        },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })

  // Roles que quien consulta puede asignar: sirven para el selector y para saber a quién puede gestionar.
  const roles = useQuery({
    queryKey: ['assignable-roles', entidad.id],
    enabled: gestiona,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/entities/{entidad_id}/assignable-roles/', {
        params: { path: { entidad_id: entidad.id } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })

  const refrescar = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['members', entidad.id] }),
      queryClient.invalidateQueries({ queryKey: ['entity-invitations', entidad.id] }),
    ])

  const reactivar = useMutation({
    mutationFn: async (miembro: Miembro) => {
      const { data, error, response } = await api.PATCH('/api/entities/{entidad_id}/members/{id}/', {
        params: { path: { entidad_id: entidad.id, id: miembro.id } },
        body: { activa: true },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
    onSuccess: (miembro) => {
      setAviso({ tipo: 'ok', texto: `Se reactivó a ${nombreDe(miembro)}.` })
      void refrescar()
    },
    onError: (e) => setAviso({ tipo: 'error', texto: mensajeDeError(e, 'No se pudo reactivar.') }),
  })

  const asignables = new Set((roles.data ?? []).map((r) => r.id))
  const puedeGestionar = (m: Miembro) => gestiona && asignables.has(m.rol) && m.usuario !== me.data?.id
  const filas = miembros.data ?? []

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
          <Button onClick={() => setAgregando(true)}>
            <UserPlus />
            Agregar miembro
          </Button>
        )}
      </div>

      {archivada && entidad.puede_gestionar_miembros && (
        <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
          La entidad está archivada: no se pueden agregar ni modificar miembros.
        </p>
      )}

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
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{mensajeDeError(miembros.error, 'No se pudieron cargar los miembros.')}</p>
          <Button variant="outline" onClick={() => miembros.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {miembros.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          Esta entidad todavía no tiene miembros.
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Miembros de {entidad.nombre}</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Persona</th>
                <th scope="col" className="px-4 py-2 font-medium">Rol</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
                {gestiona && (
                  <th scope="col" className="px-4 py-2 text-right font-medium">Acciones</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((m) => {
                const activo = m.activa !== false
                return (
                  <tr key={m.id} className={cn(!activo && 'text-muted-foreground')}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{nombreDe(m)}</p>
                      <p className="text-xs text-muted-foreground">
                        @{m.username}
                        {m.email && ` · ${m.email}`}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" title={m.nivel ? `Nivel ${m.nivel}` : undefined}>
                        {m.rol_nombre}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={activo ? 'secondary' : 'outline'}>{activo ? 'Activo' : 'Inactivo'}</Badge>
                    </td>
                    {gestiona && (
                      <td className="px-4 py-3">
                        {puedeGestionar(m) && (
                          <div className="flex justify-end gap-2">
                            {activo ? (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  aria-label={`Cambiar el rol de ${nombreDe(m)}`}
                                  onClick={() => setCambiando(m)}
                                >
                                  Cambiar rol
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  aria-label={`Desactivar a ${nombreDe(m)}`}
                                  onClick={() => setDesactivando(m)}
                                >
                                  Desactivar
                                </Button>
                              </>
                            ) : (
                              <Button
                                variant="outline"
                                size="sm"
                                aria-label={`Reactivar a ${nombreDe(m)}`}
                                disabled={reactivar.isPending}
                                onClick={() => {
                                  setAviso(null)
                                  reactivar.mutate(m)
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
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <InvitacionesPendientes
        entidadId={entidad.id}
        rolesGestionables={asignables}
        puedeGestionar={gestiona}
      />

      <AccionesMiembroDialogs
        entidadId={entidad.id}
        roles={roles.data ?? []}
        agregando={agregando}
        cambiando={cambiando}
        desactivando={desactivando}
        onCerrar={() => {
          setAgregando(false)
          setCambiando(null)
          setDesactivando(null)
        }}
        onAviso={(texto) => {
          setAviso({ tipo: 'ok', texto })
          void refrescar()
        }}
      />
    </div>
  )
}
