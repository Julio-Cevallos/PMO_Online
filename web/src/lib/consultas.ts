import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError } from '@/lib/errores'
import type { TipoEntidad } from '@/lib/tipos'

/**
 * Tipos de entidad (Proyecto, Sucursal…). Solo los puede leer el Admin o quien ya es miembro de
 * alguna entidad: use `enabled` para no pedirlos (daría 403) cuando no corresponde.
 */
export function useTiposEntidad(enabled = true) {
  return useQuery({
    queryKey: ['entity-types'],
    enabled,
    retry: false,
    queryFn: async (): Promise<TipoEntidad[]> => {
      const { data, error, response } = await api.GET('/api/entity-types/')
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Cuentas de usuario (solo quien gestiona usuarios), de 50 en 50. `soloActivos` filtra las desactivadas. */
export function useUsuarios(pagina: number, soloActivos: boolean, enabled = true) {
  return useQuery({
    queryKey: ['users', pagina, soloActivos],
    enabled,
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/users/', {
        params: { query: { page: pagina, ...(soloActivos ? { is_active: true } : {}) } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

export interface FiltrosAuditoria {
  entidad?: number
  portafolio?: number
  categoria?: 'sistema' | 'entidad' | 'contenido'
  /** Prefijo de acción (`usuario.`, `miembro.`…). */
  accion?: string
  desde?: string
  hasta?: string
}

/** Historial de auditoría visible para la persona (el backend filtra según sus permisos), de 50 en 50. */
export function useEventosAuditoria(filtros: FiltrosAuditoria, pagina: number, enabled = true) {
  return useQuery({
    queryKey: ['audit', filtros, pagina],
    enabled,
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/audit/', {
        params: { query: { ...filtros, page: pagina } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Máximo de cuentas que devuelve la búsqueda (el backend lo aplica igual). */
export const LIMITE_CANDIDATOS = 10

/** Cuentas que la persona puede sumar a una entidad, filtradas por `texto` (usuario o nombre). */
export function useCandidatos(entidadId: number, texto: string, enabled = true) {
  return useQuery({
    queryKey: ['candidates', entidadId, texto],
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/entities/{entidad_id}/candidates/', {
        params: { path: { entidad_id: entidadId }, query: texto ? { q: texto } : {} },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Invitaciones pendientes de la persona con sesión (las que puede aceptar o rechazar). */
export function useMisInvitaciones(enabled = true) {
  return useQuery({
    queryKey: ['my-invitations'],
    enabled,
    retry: false,
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/invitations/')
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Invitaciones pendientes de una entidad (solo quien puede ver sus miembros). */
export function useInvitacionesEntidad(entidadId: number, enabled = true) {
  return useQuery({
    queryKey: ['entity-invitations', entidadId],
    enabled,
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/entities/{entidad_id}/invitations/', {
        params: { path: { entidad_id: entidadId } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Portafolios que la persona ve (el Admin, todos): grupos de entidades gestionados en conjunto. */
export function usePortafolios(enabled = true) {
  return useQuery({
    queryKey: ['portfolios'],
    enabled,
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolios/')
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

export function usePortafolio(id: number) {
  return useQuery({
    queryKey: ['portfolio', id],
    enabled: Number.isInteger(id),
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolios/{id}/', {
        params: { path: { id } },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}

/** Invitaciones a portafolios pendientes de la persona con sesión. */
export function useMisInvitacionesPortafolio(enabled = true) {
  return useQuery({
    queryKey: ['my-portfolio-invitations'],
    enabled,
    retry: false,
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/portfolio-invitations/')
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
  })
}
