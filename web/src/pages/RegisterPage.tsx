import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { AuthLayout } from '@/components/AuthLayout'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { APP_NAME } from '@/config'
import { api, firstMessage, type ApiErrors } from '@/lib/api'

const schema = z
  .object({
    username: z.string().min(1, 'Elige un nombre de usuario').max(150),
    email: z.union([z.literal(''), z.email('Ingresa un correo válido')]),
    password: z.string().min(8, 'Mínimo 8 caracteres'),
    confirmPassword: z.string().min(1, 'Repite la contraseña'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Las contraseñas no coinciden',
  })
type FormValues = z.infer<typeof schema>

type RegisterField = 'username' | 'email' | 'password'
const SERVER_FIELDS: RegisterField[] = ['username', 'email', 'password']

export function RegisterPage() {
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const createAccount = useMutation({
    mutationFn: async ({ username, email, password }: FormValues) => {
      const { response, error } = await api.POST('/api/auth/register/', {
        body: { username, password, ...(email ? { email } : {}) },
      })
      if (!response.ok) {
        const apiErrors = (error ?? {}) as ApiErrors
        let shown = false
        for (const field of SERVER_FIELDS) {
          const message = firstMessage(apiErrors[field])
          if (message) {
            setError(field, { message })
            shown = true
          }
        }
        if (!shown) throw new Error('No se pudo crear la cuenta. Intenta de nuevo.')
        return false
      }
      return true
    },
    onSuccess: (created) => {
      if (created) navigate('/login', { state: { registered: true } })
    },
    onError: (error: Error) => setServerError(error.message),
  })

  return (
    <AuthLayout title="Crear cuenta" description={`Regístrate para empezar a usar ${APP_NAME}.`}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={handleSubmit((values) => {
          setServerError(null)
          createAccount.mutate(values)
        })}
      >
        <FormField
          id="username"
          label="Usuario"
          autoComplete="username"
          error={errors.username?.message}
          {...register('username')}
        />
        <FormField
          id="email"
          label="Correo electrónico (opcional)"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register('email')}
        />
        <FormField
          id="password"
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <FormField
          id="confirmPassword"
          label="Repetir contraseña"
          type="password"
          autoComplete="new-password"
          error={errors.confirmPassword?.message}
          {...register('confirmPassword')}
        />
        {serverError && (
          <p role="alert" className="text-sm text-destructive">
            {serverError}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={createAccount.isPending}>
          {createAccount.isPending ? 'Creando…' : 'Crear cuenta'}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="font-medium text-foreground underline underline-offset-4">
            Iniciar sesión
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
