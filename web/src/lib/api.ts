import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from '@api-client/schema'
import { getAccessToken } from '@/lib/auth'

const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Agrega el JWT a cada petición si hay sesión (equivale a un DelegatingHandler en .NET).
const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getAccessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
}

export const api = createClient<paths>({ baseUrl })
api.use(authMiddleware)

/** Errores de validación de DRF: { campo: ["mensaje", ...], detail?: "..." } */
export type ApiErrors = Record<string, string[] | string | undefined>

export function firstMessage(value: string[] | string | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}
