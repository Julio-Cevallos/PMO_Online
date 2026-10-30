import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { NuevaEntidadDialog } from '@/components/entidades/NuevaEntidad'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { usePortafolios, useTiposEntidad } from '@/lib/consultas'
import { tienePermiso, useMe } from '@/lib/session'

type Estado = '' | 'activa' | 'archivada'

const ETIQUETA_ESTADO = { activa: 'Activa', archivada: 'Archivada' } as const

/** Lista de las entidades que la persona puede ver (el Admin ve todas), con filtros y páginas. */
export function EntidadesPage() {
  const me = useMe()
  const [tipo, setTipo] = useState('')
  const [estado, setEstado] = useState<Estado>('')
  const [portafolio, setPortafolio] = useState('')
  const [page, setPage] = useState(1)
  const [creando, setCreando] = useState(false)

  const entidades = useQuery({
    queryKey: ['entities', { tipo, estado, portafolio, page }],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await api.GET('/api/entities/', {
        params: {
          query: {
            tipo: tipo ? Number(tipo) : undefined,
            estado: estado || undefined,
            portafolio: portafolio ? Number(portafolio) : undefined,
            page,
          },
        },
      })
      if (!data) throw new Error('No se pudieron cargar las entidades.')
      return data
    },
  })

  const esAdmin = Boolean(me.data?.is_admin || me.data?.is_superuser)
  // Crean entidades el Admin, el Moderador (en su portafolio personal) y quien tenga ese permiso en un portafolio.
  const portafolios = usePortafolios()
  const creables = (portafolios.data ?? []).filter(
    (p) => p.puede_crear_entidades && !(p.personal && p.creado_por === me.data?.id),
  )
  const permitePersonal = tienePermiso(me.data, 'entities.create_entity')
  const puedeCrear = permitePersonal || creables.length > 0

  // Los tipos solo los pueden leer quienes crean entidades y quienes ya son miembros de alguna;
  // para el resto se omite la consulta (daría 403) y el filtro queda sin opciones.
  const tipos = useTiposEntidad(puedeCrear || (entidades.data?.count ?? 0) > 0)

  const hayFiltros = tipo !== '' || estado !== '' || portafolio !== ''
  const filas = entidades.data?.results ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Entidades</h1>
          <p className="text-sm text-muted-foreground">
            {esAdmin
              ? 'Todas las entidades del sistema.'
              : puedeCrear
                ? 'Las entidades que creaste y aquellas de las que eres miembro.'
                : 'Los proyectos, sucursales y demás entidades de las que eres miembro.'}
          </p>
        </div>
        {puedeCrear && (
          <Button className="shrink-0" onClick={() => setCreando(true)}>
            <Plus />
            Nueva entidad
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="filtro-tipo">Tipo</Label>
          <Select
            id="filtro-tipo"
            value={tipo}
            onChange={(e) => {
              setTipo(e.target.value)
              setPage(1)
            }}
          >
            <option value="">Todos</option>
            {tipos.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="filtro-estado">Estado</Label>
          <Select
            id="filtro-estado"
            value={estado}
            onChange={(e) => {
              setEstado(e.target.value as Estado)
              setPage(1)
            }}
          >
            <option value="">Todos</option>
            <option value="activa">Activas</option>
            <option value="archivada">Archivadas</option>
          </Select>
        </div>
        {(portafolios.data?.length ?? 0) > 1 && (
          <div className="space-y-1.5">
            <Label htmlFor="filtro-portafolio">Portafolio</Label>
            <Select
              id="filtro-portafolio"
              value={portafolio}
              onChange={(e) => {
                setPortafolio(e.target.value)
                setPage(1)
              }}
            >
              <option value="">Todos</option>
              {portafolios.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                  {p.personal ? ' (personal)' : ''}
                </option>
              ))}
            </Select>
          </div>
        )}
        {hayFiltros && (
          <Button
            variant="ghost"
            onClick={() => {
              setTipo('')
              setEstado('')
              setPortafolio('')
              setPage(1)
            }}
          >
            Quitar filtros
          </Button>
        )}
      </div>

      {entidades.isPending && <p className="text-muted-foreground">Cargando…</p>}

      {entidades.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-destructive">{entidades.error.message}</p>
          <Button variant="outline" onClick={() => entidades.refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {entidades.data && filas.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          {hayFiltros
            ? 'Ninguna entidad coincide con los filtros.'
            : puedeCrear
              ? 'Todavía no hay entidades. Crea la primera con «Nueva entidad».'
              : 'Todavía no perteneces a ninguna entidad. Pídele a un administrador o al responsable de la entidad que te invite; verás la invitación en la sección Invitaciones.'}
        </p>
      )}

      {filas.length > 0 && (
        <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Nombre</th>
                <th scope="col" className="px-4 py-2 font-medium">Tipo</th>
                <th scope="col" className="px-4 py-2 font-medium">Portafolio</th>
                <th scope="col" className="px-4 py-2 font-medium">Estado</th>
                <th scope="col" className="px-4 py-2 font-medium">Mi rol</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-3">
                    <Link to={`/entities/${e.id}`} className="font-medium hover:underline">
                      {e.nombre}
                    </Link>
                    {e.descripcion && (
                      <p className="line-clamp-1 text-xs text-muted-foreground">{e.descripcion}</p>
                    )}
                  </td>
                  <td className="px-4 py-3">{e.tipo_nombre}</td>
                  <td className="px-4 py-3 text-muted-foreground">{e.portafolio_nombre}</td>
                  <td className="px-4 py-3">
                    <Badge variant={e.estado === 'archivada' ? 'outline' : 'secondary'}>
                      {ETIQUETA_ESTADO[e.estado ?? 'activa']}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{e.mi_rol ?? '—'}</td>
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
        portafolios={creables}
        permitePersonal={permitePersonal}
        onClose={() => setCreando(false)}
      />
    </div>
  )
}
