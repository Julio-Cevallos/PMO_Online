import { ArrowLeft } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { HistorialEventos } from '@/components/auditoria/HistorialEventos'
import { DatosPortafolio } from '@/components/portafolios/DatosPortafolio'
import { EntidadesDelPortafolio } from '@/components/portafolios/EntidadesDelPortafolio'
import { MiembrosPortafolio } from '@/components/portafolios/MiembrosPortafolio'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePortafolio } from '@/lib/consultas'
import { ErrorDeApi } from '@/lib/errores'
import { cn } from '@/lib/utils'

type Pestana = 'entidades' | 'miembros' | 'historial' | 'datos'

const ETIQUETAS: Record<Pestana, string> = {
  entidades: 'Entidades',
  miembros: 'Miembros',
  historial: 'Historial',
  datos: 'Datos',
}

/** Detalle de un portafolio: sus entidades, sus miembros, su historial y sus datos. */
export function PortafolioDetallePage() {
  const { id } = useParams()
  const portafolioId = Number(id)
  const [params, setParams] = useSearchParams()
  const portafolio = usePortafolio(portafolioId)

  const volver = (
    <Link
      to="/portfolios"
      className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Portafolios
    </Link>
  )

  if (portafolio.isPending) return <p className="text-muted-foreground">Cargando…</p>

  if (portafolio.isError) {
    const noEncontrado = portafolio.error instanceof ErrorDeApi && portafolio.error.info.status === 404
    return (
      <div className="space-y-4">
        {volver}
        <div role="alert" className="space-y-2">
          <p className="text-destructive">
            {noEncontrado
              ? 'No encontramos este portafolio o no tienes acceso a él.'
              : 'No se pudo cargar el portafolio.'}
          </p>
          {!noEncontrado && (
            <Button variant="outline" onClick={() => portafolio.refetch()}>
              Reintentar
            </Button>
          )}
        </div>
      </div>
    )
  }

  const p = portafolio.data
  const pestanas: Pestana[] = [
    'entidades',
    ...(p.puede_ver_miembros ? (['miembros'] as const) : []),
    ...(p.puede_ver_historial ? (['historial'] as const) : []),
    'datos',
  ]
  const pedida = params.get('pestana')
  const pestana = pestanas.find((x) => x === pedida) ?? 'entidades'

  return (
    <div className="space-y-6">
      {volver}

      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{p.nombre}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {p.personal && <Badge variant="outline">Personal</Badge>}
          <Badge variant="secondary">{p.total_entidades} entidades</Badge>
          {p.mi_rol && <Badge variant="outline">Mi rol: {p.mi_rol}</Badge>}
        </div>
        {p.descripcion && <p className="text-sm text-muted-foreground">{p.descripcion}</p>}
      </div>

      <div role="tablist" aria-label="Secciones del portafolio" className="flex gap-1 border-b">
        {pestanas.map((x) => (
          <button
            key={x}
            type="button"
            role="tab"
            id={`pestana-pf-${x}`}
            aria-selected={pestana === x}
            aria-controls="panel-portafolio"
            onClick={() => setParams(x === 'entidades' ? {} : { pestana: x }, { replace: true })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm transition-colors',
              pestana === x
                ? 'border-foreground font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {ETIQUETAS[x]}
          </button>
        ))}
      </div>

      <div id="panel-portafolio" role="tabpanel" aria-labelledby={`pestana-pf-${pestana}`}>
        {pestana === 'entidades' && <EntidadesDelPortafolio portafolio={p} />}
        {pestana === 'miembros' && <MiembrosPortafolio portafolio={p} />}
        {pestana === 'historial' && <HistorialEventos portafolioId={p.id} />}
        {pestana === 'datos' && <DatosPortafolio key={p.id} portafolio={p} />}
      </div>
    </div>
  )
}
