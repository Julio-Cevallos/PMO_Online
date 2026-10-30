import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { HistorialEventos } from '@/components/auditoria/HistorialEventos'
import { DatosEntidad } from '@/components/entidades/DatosEntidad'
import { MiembrosPanel } from '@/components/entidades/MiembrosPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const NO_ENCONTRADA = 'not-found'

type Pestana = 'datos' | 'miembros' | 'historial'

const ETIQUETAS: Record<Pestana, string> = { datos: 'Datos', miembros: 'Miembros', historial: 'Historial' }

/** Detalle de una entidad: sus datos y, si el rol lo permite, sus miembros. */
export function EntidadDetallePage() {
  const { id } = useParams()
  const entidadId = Number(id)
  const [params, setParams] = useSearchParams()

  const entidad = useQuery({
    queryKey: ['entity', entidadId],
    enabled: Number.isInteger(entidadId),
    retry: false,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/entities/{id}/', {
        params: { path: { id: entidadId } },
      })
      if (response.status === 404) throw new Error(NO_ENCONTRADA)
      if (!data) throw new Error('error')
      return data
    },
  })

  const volver = (
    <Link
      to="/entities"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Entidades
    </Link>
  )

  if (!Number.isInteger(entidadId) || (entidad.isError && entidad.error.message === NO_ENCONTRADA)) {
    return (
      <div className="space-y-4">
        {volver}
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No encontramos esta entidad o no tienes acceso a ella.
        </p>
      </div>
    )
  }

  if (entidad.isPending) return <p className="text-muted-foreground">Cargando…</p>

  if (entidad.isError) {
    return (
      <div className="space-y-4">
        {volver}
        <div role="alert" className="space-y-2">
          <p className="text-destructive">No se pudo cargar la entidad.</p>
          <Button variant="outline" onClick={() => entidad.refetch()}>
            Reintentar
          </Button>
        </div>
      </div>
    )
  }

  const e = entidad.data
  const pestanas: Pestana[] = [
    'datos',
    ...(e.puede_ver_miembros ? (['miembros'] as const) : []),
    ...(e.puede_ver_historial ? (['historial'] as const) : []),
  ]
  const hayPestanas = pestanas.length > 1
  const pedida = params.get('pestana')
  const pestana = pestanas.find((p) => p === pedida) ?? 'datos'
  const elegir = (p: Pestana) => setParams(p === 'datos' ? {} : { pestana: p }, { replace: true })

  return (
    <div className="space-y-6">
      {volver}

      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{e.nombre}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{e.tipo_nombre}</Badge>
          <Badge variant={e.estado === 'archivada' ? 'outline' : 'secondary'}>
            {e.estado === 'archivada' ? 'Archivada' : 'Activa'}
          </Badge>
          {e.mi_rol && <Badge variant="outline">Mi rol: {e.mi_rol}</Badge>}
        </div>
      </div>

      {hayPestanas && (
        <div role="tablist" aria-label="Secciones de la entidad" className="flex gap-1 border-b">
          {pestanas.map((p) => (
            <button
              key={p}
              type="button"
              role="tab"
              id={`pestana-${p}`}
              aria-selected={pestana === p}
              aria-controls="panel-entidad"
              onClick={() => elegir(p)}
              className={cn(
                '-mb-px border-b-2 px-3 py-2 text-sm transition-colors',
                pestana === p
                  ? 'border-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {ETIQUETAS[p]}
            </button>
          ))}
        </div>
      )}

      <div id="panel-entidad" role={hayPestanas ? 'tabpanel' : undefined} aria-labelledby={hayPestanas ? `pestana-${pestana}` : undefined}>
        {pestana === 'datos' && <DatosEntidad entidad={e} />}
        {pestana === 'miembros' && <MiembrosPanel entidad={e} />}
        {pestana === 'historial' && <HistorialEventos entidadId={e.id} />}
      </div>
    </div>
  )
}
