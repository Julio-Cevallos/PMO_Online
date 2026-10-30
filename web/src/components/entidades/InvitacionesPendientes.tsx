import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useInvitacionesEntidad } from '@/lib/consultas'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import { nombreDeUsuario, type Invitacion } from '@/lib/tipos'

interface Props {
  entidadId: number
  /** Ids de los roles que quien consulta puede gestionar: solo esas invitaciones se pueden cancelar. */
  rolesGestionables: Set<number>
  puedeGestionar: boolean
}

const fecha = (iso: string) => new Date(iso).toLocaleDateString('es-EC', { dateStyle: 'medium' })

/** Invitaciones enviadas que la persona aún no responde. No se muestra si no hay ninguna. */
export function InvitacionesPendientes({ entidadId, rolesGestionables, puedeGestionar }: Props) {
  const queryClient = useQueryClient()
  const invitaciones = useInvitacionesEntidad(entidadId)
  const [error, setError] = useState<string | null>(null)

  const cancelar = useMutation({
    mutationFn: async (i: Invitacion) => {
      const { error: cuerpo, response } = await api.DELETE('/api/entities/{entidad_id}/invitations/{id}/', {
        params: { path: { entidad_id: entidadId, id: i.id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['entity-invitations', entidadId] }),
    onError: (e) => setError(mensajeDeError(e, 'No se pudo cancelar la invitación.')),
  })

  const filas = invitaciones.data ?? []
  if (invitaciones.isError || filas.length === 0) return null

  return (
    <section aria-labelledby="titulo-invitaciones" className="space-y-2">
      <h2 id="titulo-invitaciones" className="text-sm font-medium">
        Invitaciones pendientes ({filas.length})
      </h2>
      <p className="text-xs text-muted-foreground">
        Entran como miembros cuando aceptan. Hasta entonces no tienen acceso a la entidad.
      </p>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <ul className="divide-y rounded-xl ring-1 ring-foreground/10">
        {filas.map((i) => (
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
              {puedeGestionar && rolesGestionables.has(i.rol) && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Cancelar la invitación a ${i.username}`}
                  disabled={cancelar.isPending}
                  onClick={() => {
                    setError(null)
                    cancelar.mutate(i)
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
  )
}
