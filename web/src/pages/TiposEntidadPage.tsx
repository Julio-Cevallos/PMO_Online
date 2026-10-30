import { useState } from 'react'
import { Plus } from 'lucide-react'
import { EliminarTipoDialog, TipoDialog } from '@/components/tipos/AccionesTipo'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useTiposEntidad } from '@/lib/consultas'
import { mensajeDeError } from '@/lib/errores'
import { tienePermiso, useMe } from '@/lib/session'
import type { TipoEntidad } from '@/lib/tipos'
import { cn } from '@/lib/utils'

const si = (valor: boolean | undefined) => (valor ? 'Sí' : 'No')

/** Administración de los tipos de entidad (solo quien tiene el permiso global de gestionarlos). */
export function TiposEntidadPage() {
  const me = useMe()
  const permitido = tienePermiso(me.data, 'entities.manage_types')
  const tipos = useTiposEntidad(permitido)
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<TipoEntidad | null>(null)
  const [eliminando, setEliminando] = useState<TipoEntidad | null>(null)

  if (me.data && !permitido) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        No tienes acceso a esta sección.
      </p>
    )
  }

  const filas = tipos.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Tipos de entidad</h1>
          <p className="text-sm text-muted-foreground">
            Las categorías de entidad: proyectos, sucursales, proveedores… Cada entidad pertenece a un tipo.
          </p>
        </div>
        <Button className="shrink-0" onClick={() => setCreando(true)}>
          <Plus />
          Nuevo tipo
        </Button>
      </div>

      {tipos.isPending && <p className="text-muted-foreground">Cargando…</p>}

      {tipos.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{mensajeDeError(tipos.error, 'No se pudieron cargar los tipos.')}</p>
          <Button variant="outline" onClick={() => tipos.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {tipos.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          Todavía no hay tipos de entidad.
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Tipos de entidad</caption>
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Tipo</th>
                <th scope="col" className="px-4 py-2 font-medium">Admite tareas</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
                <th scope="col" className="px-4 py-2 font-medium">Entidades</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((t) => {
                const activo = t.activo !== false
                return (
                  <tr key={t.id} className={cn(!activo && 'text-muted-foreground')}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{t.nombre}</p>
                      <p className="text-xs text-muted-foreground">{t.nombre_plural}</p>
                    </td>
                    <td className="px-4 py-3">{si(t.admite_tareas)}</td>
                    <td className="px-4 py-3">
                      <Badge variant={activo ? 'secondary' : 'outline'}>{activo ? 'Activo' : 'Inactivo'}</Badge>
                    </td>
                    <td className="px-4 py-3">{t.total_entidades}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          aria-label={`Editar el tipo ${t.nombre}`}
                          onClick={() => setEditando(t)}
                        >
                          Editar
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`Eliminar el tipo ${t.nombre}`}
                          disabled={t.total_entidades > 0}
                          title={
                            t.total_entidades > 0
                              ? 'Tiene entidades: desactívalo en lugar de eliminarlo'
                              : undefined
                          }
                          onClick={() => setEliminando(t)}
                        >
                          Eliminar
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <TipoDialog open={creando} tipo={null} onClose={() => setCreando(false)} />
      <TipoDialog open={editando !== null} tipo={editando} onClose={() => setEditando(null)} />
      <EliminarTipoDialog tipo={eliminando} onClose={() => setEliminando(null)} />
    </div>
  )
}
