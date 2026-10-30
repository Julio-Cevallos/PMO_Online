import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, FolderKanban, LogOut, Mail, Menu, ScrollText, Tags, Users, X, type LucideIcon } from 'lucide-react'
import { NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { APP_NAME } from '@/config'
import { api } from '@/lib/api'
import { clearTokens, getAccessToken, getRefreshToken } from '@/lib/auth'
import { useMisInvitaciones, useMisInvitacionesPortafolio, usePortafolios } from '@/lib/consultas'
import { SESSION_EXPIRED, tienePermiso, useMe } from '@/lib/session'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Permiso global necesario para ver el elemento (si no se indica, lo ven todos). */
  permission?: string
}

/** Cada módulo nuevo agrega aquí su entrada; el menú solo muestra las que la persona puede usar. */
const NAV_ITEMS: NavItem[] = [
  { to: '/entities', label: 'Entidades', icon: Building2 },
  { to: '/portfolios', label: 'Portafolios', icon: FolderKanban },
  { to: '/invitations', label: 'Invitaciones', icon: Mail },
  { to: '/users', label: 'Usuarios', icon: Users, permission: 'accounts.manage_users' },
  { to: '/audit', label: 'Auditoría', icon: ScrollText, permission: 'audit.view_system_log' },
  { to: '/entity-types', label: 'Tipos de entidad', icon: Tags, permission: 'entities.manage_types' },
]

/** Estructura de las pantallas con sesión: menú lateral, encabezado en celular y contenido. */
export function AppLayout() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [menuOpen, setMenuOpen] = useState(false)
  const hasToken = getAccessToken() !== null
  const me = useMe()
  const pendientes =
    (useMisInvitaciones(hasToken).data?.length ?? 0) +
    (useMisInvitacionesPortafolio(hasToken).data?.length ?? 0)
  const portafolios = usePortafolios(hasToken)

  const expired = me.isError && me.error.message === SESSION_EXPIRED
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
  if (expired) return null
  if (me.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-muted">
        <p className="text-muted-foreground">Cargando…</p>
      </main>
    )
  }
  if (me.isError) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-muted px-4 text-center">
        <p className="text-destructive">No se pudo conectar con el servidor.</p>
        <Button variant="outline" onClick={() => me.refetch()}>
          Reintentar
        </Button>
      </main>
    )
  }

  const perfil = me.data
  const items = NAV_ITEMS.filter((i) => !i.permission || tienePermiso(perfil, i.permission)).filter(
    // Portafolios: lo ve quien pertenece a alguno o puede crearlos.
    (i) =>
      i.to !== '/portfolios' ||
      tienePermiso(perfil, 'entities.create_entity') ||
      (portafolios.data?.length ?? 0) > 0,
  )
  const nombre = [perfil.first_name, perfil.last_name].filter(Boolean).join(' ') || perfil.username

  return (
    <div className="min-h-screen bg-background text-foreground md:flex">
      {menuOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 md:hidden"
          aria-hidden="true"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform md:sticky md:inset-y-auto md:top-0 md:h-screen md:shrink-0 md:translate-x-0',
          menuOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-12 items-center justify-between px-4">
          <span className="font-semibold tracking-tight">{APP_NAME}</span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            aria-label="Cerrar menú"
            onClick={() => setMenuOpen(false)}
          >
            <X />
          </Button>
        </div>

        <nav aria-label="Principal" className="flex-1 space-y-1 px-2 py-2">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors hover:bg-sidebar-accent',
                  isActive && 'bg-sidebar-accent font-medium',
                )
              }
            >
              <Icon className="size-4" />
              {label}
              {to === '/invitations' && pendientes > 0 && (
                <Badge className="ml-auto" aria-label={`${pendientes} pendientes`}>
                  {pendientes}
                </Badge>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-2 border-t border-sidebar-border p-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{nombre}</p>
            <p className="truncate text-xs text-muted-foreground">@{perfil.username}</p>
            {(perfil.is_superuser || perfil.is_admin || perfil.is_moderator) && (
              <Badge variant="outline" className="mt-1.5">
                {perfil.is_superuser ? 'Superusuario' : perfil.is_admin ? 'Admin' : 'Moderador'}
              </Badge>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            <LogOut />
            Cerrar sesión
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 border-b px-3 md:hidden">
          <Button variant="ghost" size="icon" aria-label="Abrir menú" onClick={() => setMenuOpen(true)}>
            <Menu />
          </Button>
          <span className="font-semibold tracking-tight">{APP_NAME}</span>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
