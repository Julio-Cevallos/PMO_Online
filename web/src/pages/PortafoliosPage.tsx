import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NuevoPortafolioDialog } from '@/components/portafolios/NuevoPortafolio'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePortafolios } from '@/lib/consultas'
import { mensajeDeError } from '@/lib/errores'
import { tienePermiso, useMe } from '@/lib/session'

/** Portafolios que la persona ve: grupos de entidades que varias personas gestionan en conjunto. */
export function PortafoliosPage() {
  const me = useMe()
  const portafolios = usePortafolios()
  const [creando, setCreando] = useState(false)
  const puedeCrear = tienePermiso(me.data, 'entities.create_entity')
  const filas = portafolios.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Portafolios</h1>
          <p className="text-sm text-muted-foreground">
            Grupos de entidades que varias personas gestionan en conjunto. Quien tiene un rol en un portafolio
            trabaja con todas sus entidades.
          </p>
        </div>
        {puedeCrear && (
          <Button className="shrink-0" onClick={() => setCreando(true)}>
            <Plus />
            Nuevo portafolio
          </Button>
        )}
      </div>

      {portafolios.isPending && <p className="text-muted-foreground">Cargando…</p>}

      {portafolios.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{mensajeDeError(portafolios.error, 'No se pudieron cargar los portafolios.')}</p>
          <Button variant="outline" onClick={() => portafolios.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {portafolios.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          {puedeCrear
            ? 'Todavía no tienes portafolios. Crea uno con «Nuevo portafolio»; tu portafolio personal aparece al crear tu primera entidad.'
            : 'Todavía no perteneces a ningún portafolio. Cuando te inviten, verás la invitación en la sección Invitaciones.'}
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Portafolios</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Nombre</th>
                <th scope="col" className="px-4 py-2 font-medium">Entidades</th>
                <th scope="col" className="px-4 py-2 font-medium">Mi rol</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3">
                    <Link to={`/portfolios/${p.id}`} className="font-medium hover:underline">
                      {p.nombre}
                    </Link>
                    {p.personal && (
                      <Badge variant="outline" className="ml-2">
                        Personal
                      </Badge>
                    )}
                    {p.descripcion && (
                      <p className="line-clamp-1 text-xs text-muted-foreground">{p.descripcion}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">{p.total_entidades}</td>
                  <td className="px-4 py-3 text-muted-foreground">{p.mi_rol ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <NuevoPortafolioDialog open={creando} onClose={() => setCreando(false)} />
    </div>
  )
}
