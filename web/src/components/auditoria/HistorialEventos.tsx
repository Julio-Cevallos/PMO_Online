import { Fragment, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import {
  CATEGORIAS,
  GRUPOS_ACCION,
  cambiosDe,
  detalleDe,
  etiquetaAccion,
  etiquetaCampo,
  fechaHora,
  formatearValor,
  type EventoAuditoria,
} from '@/lib/auditoria'
import { useEventosAuditoria, type FiltrosAuditoria } from '@/lib/consultas'
import { mensajeDeError } from '@/lib/errores'

const TAMANO_PAGINA = 50

function DetalleEvento({ evento, mostrarEntidad }: { evento: EventoAuditoria; mostrarEntidad: boolean }) {
  const cambios = cambiosDe(evento)
  const detalle = detalleDe(evento)
  return (
    <div className="space-y-3 text-sm">
      {cambios.length > 0 ? (
        <table className="w-full text-left text-xs">
          <caption className="sr-only">Cambios del evento</caption>
          <thead className="text-muted-foreground uppercase">
            <tr>
              <th scope="col" className="py-1 pr-4 font-medium">Campo</th>
              <th scope="col" className="py-1 pr-4 font-medium">Antes</th>
              <th scope="col" className="py-1 font-medium">Después</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {cambios.map((c) => (
              <tr key={c.campo}>
                <th scope="row" className="py-1 pr-4 align-top font-medium">{etiquetaCampo(c.campo)}</th>
                <td className="py-1 pr-4 align-top break-words">{formatearValor(c.antes)}</td>
                <td className="py-1 align-top break-words">{formatearValor(c.despues)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-muted-foreground">Este evento no registra cambios de campos.</p>
      )}
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {detalle.map(([clave, valor]) => (
          <div key={clave} className="flex gap-2">
            <dt className="text-muted-foreground">{etiquetaCampo(clave)}:</dt>
            <dd className="break-words">{valor}</dd>
          </div>
        ))}
        <div className="flex gap-2">
          <dt className="text-muted-foreground">Dirección IP:</dt>
          <dd>{evento.ip ?? '—'}</dd>
        </div>
        {mostrarEntidad && evento.entidad_nombre && (
          <div className="flex gap-2">
            <dt className="text-muted-foreground">Entidad:</dt>
            <dd>{evento.entidad_nombre}</dd>
          </div>
        )}
        <div className="flex gap-2">
          <dt className="text-muted-foreground">Evento n.º:</dt>
          <dd>{evento.id}</dd>
        </div>
      </dl>
    </div>
  )
}

interface Props {
  /** Si se indica, solo se muestra el historial de esa entidad (pestaña "Historial" del detalle). */
  entidadId?: number
  /** Si se indica, solo el historial de ese portafolio y sus entidades. */
  portafolioId?: number
}

/** Historial de auditoría con filtros y detalle de cada evento. Solo lectura. */
export function HistorialEventos({ entidadId, portafolioId }: Props) {
  const [categoria, setCategoria] = useState('')
  const [accion, setAccion] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [pagina, setPagina] = useState(1)
  const [abierto, setAbierto] = useState<number | null>(null)

  const filtros: FiltrosAuditoria = {
    ...(entidadId !== undefined ? { entidad: entidadId } : {}),
    ...(portafolioId !== undefined ? { portafolio: portafolioId } : {}),
    ...(categoria ? { categoria: categoria as FiltrosAuditoria['categoria'] } : {}),
    ...(accion ? { accion } : {}),
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
  }
  const eventos = useEventosAuditoria(filtros, pagina)
  const filas = eventos.data?.results ?? []
  const total = eventos.data?.count ?? 0
  const paginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA))
  const hayFiltros = Boolean(categoria || accion || desde || hasta)
  const mostrarEntidad = entidadId === undefined
  const rangoInvalido = Boolean(desde && hasta && desde > hasta)

  const cambiar = (poner: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    poner(e.target.value)
    setPagina(1)
    setAbierto(null)
  }

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-end gap-3"
        aria-label="Filtros del historial"
        onSubmit={(e) => e.preventDefault()}
      >
        <div className="space-y-1">
          <label htmlFor="aud-categoria" className="block text-xs text-muted-foreground">Categoría</label>
          <Select id="aud-categoria" value={categoria} onChange={cambiar(setCategoria)}>
            <option value="">Todas</option>
            {CATEGORIAS.map((c) => (
              <option key={c.valor} value={c.valor}>{c.etiqueta}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label htmlFor="aud-accion" className="block text-xs text-muted-foreground">Qué pasó con…</label>
          <Select id="aud-accion" value={accion} onChange={cambiar(setAccion)}>
            <option value="">Todo</option>
            {GRUPOS_ACCION.map((g) => (
              <option key={g.prefijo} value={g.prefijo}>{g.etiqueta}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label htmlFor="aud-desde" className="block text-xs text-muted-foreground">Desde</label>
          <Input id="aud-desde" type="date" value={desde} max={hasta || undefined} onChange={cambiar(setDesde)} className="w-auto" />
        </div>
        <div className="space-y-1">
          <label htmlFor="aud-hasta" className="block text-xs text-muted-foreground">Hasta</label>
          <Input id="aud-hasta" type="date" value={hasta} min={desde || undefined} onChange={cambiar(setHasta)} className="w-auto" />
        </div>
        {hayFiltros && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setCategoria('')
              setAccion('')
              setDesde('')
              setHasta('')
              setPagina(1)
              setAbierto(null)
            }}
          >
            Quitar filtros
          </Button>
        )}
      </form>

      {rangoInvalido && (
        <p role="alert" className="text-sm text-destructive">
          La fecha «Desde» no puede ser posterior a «Hasta».
        </p>
      )}

      {eventos.isPending && <p className="text-muted-foreground">Cargando…</p>}

      {eventos.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{mensajeDeError(eventos.error, 'No se pudo cargar el historial.')}</p>
          <Button variant="outline" onClick={() => eventos.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {eventos.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          {hayFiltros ? 'No hay eventos con esos filtros.' : 'Todavía no hay eventos registrados.'}
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Historial de auditoría</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Fecha</th>
                <th scope="col" className="px-4 py-2 font-medium">Quién</th>
                <th scope="col" className="px-4 py-2 font-medium">Qué pasó</th>
                <th scope="col" className="px-4 py-2 font-medium">Sobre</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Detalle</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((ev) => {
                const abiertoAhora = abierto === ev.id
                return (
                  <Fragment key={ev.id}>
                    <tr>
                      <td className="px-4 py-3 whitespace-nowrap">{fechaHora(ev.ocurrido_en)}</td>
                      <td className="px-4 py-3">{ev.usuario_nombre || '—'}</td>
                      <td className="px-4 py-3">
                        <p className="font-medium">{etiquetaAccion(ev.accion)}</p>
                        <Badge variant="outline" className="mt-1">{ev.categoria_nombre}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <p>{ev.objeto_nombre || '—'}</p>
                        {mostrarEntidad && ev.entidad_nombre && (
                          <p className="text-xs text-muted-foreground">en {ev.entidad_nombre}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-expanded={abiertoAhora}
                          aria-controls={`evento-${ev.id}`}
                          aria-label={`${abiertoAhora ? 'Ocultar' : 'Ver'} el detalle del evento ${ev.id}`}
                          onClick={() => setAbierto(abiertoAhora ? null : ev.id)}
                        >
                          {abiertoAhora ? 'Ocultar' : 'Ver'}
                        </Button>
                      </td>
                    </tr>
                    {abiertoAhora && (
                      <tr id={`evento-${ev.id}`} className="bg-muted/40">
                        <td colSpan={5} className="px-4 py-3">
                          <DetalleEvento evento={ev} mostrarEntidad={mostrarEntidad} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {paginas > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Página {pagina} de {paginas} ({total} eventos)
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
    </div>
  )
}
