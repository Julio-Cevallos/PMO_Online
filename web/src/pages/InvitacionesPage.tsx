import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useMisInvitaciones, useMisInvitacionesPortafolio } from '@/lib/consultas'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'

interface Resultado {
  tipo: 'ok' | 'error'
  texto: string
  enlace?: string
}

type Accion = 'accept' | 'reject'

/** Lo que hace falta para mostrar y responder una invitación, sea a una entidad o a un portafolio. */
interface Item {
  clave: string
  id: number
  destino: 'entidad' | 'portafolio'
  nombre: string
  etiqueta: string
  rol: string
  invitadoPor: string
  creadoEn: string
  enlace: string
}

const fecha = (iso: string) => new Date(iso).toLocaleDateString('es-EC', { dateStyle: 'medium' })

/** Invitaciones a entidades y portafolios que la persona puede aceptar o rechazar (D-27, D-29). */
export function InvitacionesPage() {
  const queryClient = useQueryClient()
  const entidades = useMisInvitaciones()
  const portafolios = useMisInvitacionesPortafolio()
  const [resultado, setResultado] = useState<Resultado | null>(null)

  const responder = useMutation({
    mutationFn: async ({ item, accion }: { item: Item; accion: Accion }) => {
      const { data, error, response } =
        item.destino === 'entidad'
          ? await api.POST(
              accion === 'accept' ? '/api/invitations/{id}/accept/' : '/api/invitations/{id}/reject/',
              { params: { path: { id: item.id } } },
            )
          : await api.POST(
              accion === 'accept'
                ? '/api/portfolio-invitations/{id}/accept/'
                : '/api/portfolio-invitations/{id}/reject/',
              { params: { path: { id: item.id } } },
            )
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return { item, accion }
    },
    onSuccess: async ({ item, accion }) => {
      setResultado(
        accion === 'accept'
          ? {
              tipo: 'ok',
              texto: `Ahora eres ${item.rol} en «${item.nombre}».`,
              enlace: item.enlace,
            }
          : { tipo: 'ok', texto: `Rechazaste la invitación a «${item.nombre}».` },
      )
      await Promise.all(
        ['my-invitations', 'my-portfolio-invitations'].map((k) => queryClient.invalidateQueries({ queryKey: [k] })),
      )
      if (accion === 'accept') {
        await Promise.all(
          ['entities', 'portfolios', 'portfolio', 'me'].map((k) => queryClient.invalidateQueries({ queryKey: [k] })),
        )
      }
    },
    onError: async (e) => {
      setResultado({ tipo: 'error', texto: mensajeDeError(e, 'No se pudo responder la invitación.') })
      await Promise.all(
        ['my-invitations', 'my-portfolio-invitations'].map((k) => queryClient.invalidateQueries({ queryKey: [k] })),
      )
    },
  })

  const items: Item[] = [
    ...(portafolios.data ?? []).map(
      (i): Item => ({
        clave: `p${i.id}`,
        id: i.id,
        destino: 'portafolio',
        nombre: i.portafolio_nombre,
        etiqueta: 'Portafolio',
        rol: i.rol_nombre,
        invitadoPor: i.invitado_por_nombre,
        creadoEn: i.creado_en,
        enlace: `/portfolios/${i.portafolio}`,
      }),
    ),
    ...(entidades.data ?? []).map(
      (i): Item => ({
        clave: `e${i.id}`,
        id: i.id,
        destino: 'entidad',
        nombre: i.entidad_nombre,
        etiqueta: i.tipo_nombre,
        rol: i.rol_nombre,
        invitadoPor: i.invitado_por_nombre,
        creadoEn: i.creado_en,
        enlace: `/entities/${i.entidad}`,
      }),
    ),
  ]
  const cargando = entidades.isPending || portafolios.isPending
  const fallo = entidades.isError ? entidades : portafolios.isError ? portafolios : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Invitaciones</h1>
        <p className="text-sm text-muted-foreground">
          Te invitaron a unirte a estas entidades y portafolios. Hasta que aceptes no tienes acceso a ellos.
        </p>
      </div>

      {resultado && (
        <p
          role={resultado.tipo === 'error' ? 'alert' : 'status'}
          className={resultado.tipo === 'error' ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'}
        >
          {resultado.texto}{' '}
          {resultado.enlace !== undefined && (
            <Link to={resultado.enlace} className="font-medium underline underline-offset-2">
              Ver ahora
            </Link>
          )}
        </p>
      )}

      {cargando && <p className="text-muted-foreground">Cargando…</p>}

      {fallo && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{mensajeDeError(fallo.error, 'No se pudieron cargar las invitaciones.')}</p>
          <Button
            variant="outline"
            onClick={() => {
              void entidades.refetch()
              void portafolios.refetch()
            }}
          >
            Reintentar
          </Button>
        </div>
      )}

      {!cargando && !fallo && items.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No tienes invitaciones pendientes.
        </p>
      )}

      {items.length > 0 && (
        <ul className="divide-y rounded-xl ring-1 ring-foreground/10">
          {items.map((i) => (
            <li key={i.clave} className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
              <div className="min-w-0 space-y-1">
                <p className="font-medium">{i.nombre}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary">{i.etiqueta}</Badge>
                  <span>Como</span>
                  <Badge variant="outline">{i.rol}</Badge>
                  <span>
                    · Te invitó {i.invitadoPor || 'alguien'} el {fecha(i.creadoEn)}
                  </span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  aria-label={`Rechazar la invitación a ${i.nombre}`}
                  disabled={responder.isPending}
                  onClick={() => {
                    setResultado(null)
                    responder.mutate({ item: i, accion: 'reject' })
                  }}
                >
                  Rechazar
                </Button>
                <Button
                  aria-label={`Aceptar la invitación a ${i.nombre}`}
                  disabled={responder.isPending}
                  onClick={() => {
                    setResultado(null)
                    responder.mutate({ item: i, accion: 'accept' })
                  }}
                >
                  Aceptar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
