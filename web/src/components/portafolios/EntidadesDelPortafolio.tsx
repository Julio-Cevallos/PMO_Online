import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NuevaEntidadDialog } from '@/components/entidades/NuevaEntidad'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useTiposEntidad } from '@/lib/consultas'
import type { Portafolio } from '@/lib/tipos'

/** Entidades del portafolio. Quien puede crear entidades en él ve «Nueva entidad». */
export function EntidadesDelPortafolio({ portafolio }: { portafolio: Portafolio }) {
  const [page, setPage] = useState(1)
  const [creando, setCreando] = useState(false)
  const tipos = useTiposEntidad()

  const entidades = useQuery({
    queryKey: ['entities', { portafolio: portafolio.id, page }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await api.GET('/api/entities/', {
        params: { query: { portafolio: portafolio.id, page } },
      })
      if (!data) throw new Error('No se pudieron cargar las entidades.')
      return data
    },
  })
  const filas = entidades.data?.results ?? []

  return (
    <div className="space-y-4">
      {portafolio.puede_crear_entidades && (
        <div className="flex justify-end">
          <Button onClick={() => setCreando(true)}>
            <Plus />
            Nueva entidad
          </Button>
        </div>
      )}

      {entidades.isPending && <p className="text-muted-foreground">Cargando…</p>}
      {entidades.isError && (
        <p role="alert" className="text-destructive">
          {entidades.error.message}
        </p>
      )}
      {entidades.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          Este portafolio todavía no tiene entidades.
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Entidades de {portafolio.nombre}</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Nombre</th>
                <th scope="col" className="px-4 py-2 font-medium">Tipo</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-3">
                    <Link to={`/entities/${e.id}`} className="font-medium hover:underline">
                      {e.nombre}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{e.tipo_nombre}</td>
                  <td className="px-4 py-3">
                    <Badge variant={e.estado === 'archivada' ? 'outline' : 'secondary'}>
                      {e.estado === 'archivada' ? 'Archivada' : 'Activa'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {entidades.data && (entidades.data.next || entidades.data.previous) && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Página {page} · {entidades.data.count} entidades
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={!entidades.data.previous || entidades.isPlaceholderData}
              onClick={() => setPage((p) => p - 1)}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              disabled={!entidades.data.next || entidades.isPlaceholderData}
              onClick={() => setPage((p) => p + 1)}
            >
              Siguiente
            </Button>
          </div>
        </div>
      )}

      <NuevaEntidadDialog
        open={creando}
        tipos={(tipos.data ?? []).filter((t) => t.activo !== false)}
        portafolios={[portafolio]}
        portafolioFijo={portafolio.id}
        permitePersonal={false}
        onClose={() => setCreando(false)}
      />
    </div>
  )
}
