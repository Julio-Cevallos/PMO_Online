import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { clearTokens, getAccessToken, getRefreshToken } from '@/lib/auth'

/** Página temporal: confirma que la sesión funciona. El menú principal vendrá después. */
export function HomePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasToken = getAccessToken() !== null

  const me = useQuery({
    queryKey: ['me'],
    enabled: hasToken,
    retry: false,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/auth/me/')
      if (response.status === 401) throw new Error('expired')
      if (!data) throw new Error('error')
      return data
    },
  })

  const expired = me.isError && me.error.message === 'expired'
  useEffect(() => {
    if (expired) {
      clearTokens()
      navigate('/login', { replace: true })
    }
  }, [expired, navigate])

  const logout = useMutation({
    mutationFn: async () => {
      const refresh = getRefreshToken()
      // Se invalida el refresh token en el servidor; si falla, igual se cierra la sesión local.
      if (refresh) await api.POST('/api/auth/logout/', { body: { refresh } }).catch(() => undefined)
    },
    onSettled: () => {
      clearTokens()
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })

  if (!hasToken) return <Navigate to="/login" replace />

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted px-4">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">PMO Online</h1>
        {me.isPending && <p className="mt-2 text-muted-foreground">Cargando…</p>}
        {me.data && (
          <p className="mt-2 text-muted-foreground">
            Sesión iniciada como <strong className="text-foreground">{me.data.username}</strong>{' '}
            {me.data.email && `(${me.data.email})`}
          </p>
        )}
        {me.isError && !expired && (
          <p className="mt-2 text-destructive">No se pudo conectar con el servidor.</p>
        )}
        <Button variant="outline" className="mt-6" disabled={logout.isPending} onClick={() => logout.mutate()}>
          Cerrar sesión
        </Button>
      </div>
    </main>
  )
}
