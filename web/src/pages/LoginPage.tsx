import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { AuthLayout } from '@/components/AuthLayout'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { APP_NAME } from '@/config'
import { api } from '@/lib/api'
import { saveTokens } from '@/lib/auth'

const schema = z.object({
  username: z.string().min(1, 'Ingresa tu usuario'),
  password: z.string().min(1, 'Ingresa tu contraseña'),
})
type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const registered = (location.state as { registered?: boolean } | null)?.registered
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const login = useMutation({
    mutationFn: async (values: FormValues) => {
      const { data, error, response } = await api.POST('/api/auth/token/', { body: values })
      if (!data) {
        // 423: cuenta bloqueada por intentos fallidos; el servidor explica cuánto falta.
        const detalle = (error as { detail?: string } | undefined)?.detail
        if (response.status === 423) {
          throw new Error(detalle ?? 'Cuenta bloqueada. Inténtalo más tarde.')
        }
        throw new Error(
          response.status === 401
            ? 'Usuario o contraseña incorrectos.'
            : 'No se pudo iniciar sesión. Intenta de nuevo.',
        )
      }
      return data
    },
    onSuccess: (tokens) => {
      saveTokens(tokens.access, tokens.refresh)
      navigate('/', { replace: true })
    },
    onError: (error: Error) => setServerError(error.message),
  })

  return (
    <AuthLayout title="Iniciar sesión" description={`Ingresa con tu cuenta de ${APP_NAME}.`}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          login.mutate(values)
        })}
      >
        {registered && !serverError && (
          <p className="rounded-lg bg-muted p-3 text-sm">Cuenta creada. Ya puedes iniciar sesión.</p>
        )}
        <FormField
          id="username"
          label="Usuario"
          autoComplete="username"
          error={errors.username?.message}
          {...register('username')}
        />
        <FormField
          id="password"
          label="Contraseña"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        {serverError && (
          <p role="alert" className="text-sm text-destructive">
            {serverError}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? 'Ingresando…' : 'Iniciar sesión'}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          ¿No tienes cuenta?{' '}
          <Link to="/register" className="font-medium text-foreground underline underline-offset-4">
            Crear cuenta
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
