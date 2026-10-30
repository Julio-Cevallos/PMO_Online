import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { getAccessToken } from '@/lib/auth'

/** Mensaje de error que indica que el token ya no sirve y hay que volver a iniciar sesión. */
export const SESSION_EXPIRED = 'expired'

/**
 * Perfil de la persona con sesión iniciada (`/api/auth/me/`).
 * El menú y las pantallas comparten esta misma consulta (misma clave de caché).
 */
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    enabled: getAccessToken() !== null,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/auth/me/')
      if (response.status === 401) throw new Error(SESSION_EXPIRED)
      if (!data) throw new Error('error')
      return data
    },
  })
}

interface Perfil {
  is_superuser: boolean
  global_permissions: string[]
}

/** ¿Tiene este permiso global? El backend ya incluye todos los del superusuario. */
export function tienePermiso(perfil: Perfil | undefined, permiso: string): boolean {
  return perfil?.global_permissions.includes(permiso) ?? false
}
