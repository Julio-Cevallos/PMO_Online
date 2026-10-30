import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Usuario } from '@/lib/tipos'
import { MENSAJE_USUARIO, REGEX_USUARIO } from '@/lib/usuario'

const campos = {
  first_name: z.string().trim().max(150, 'Máximo 150 caracteres'),
  last_name: z.string().trim().max(150, 'Máximo 150 caracteres'),
  email: z.string().trim().email('Correo no válido').or(z.literal('')),
  is_active: z.boolean(),
  is_admin: z.boolean(),
  is_moderator: z.boolean(),
}

const schemaCrear = z.object({
  ...campos,
  username: z
    .string()
    .trim()
    .min(1, 'Indica el nombre de usuario')
    .max(150, 'Máximo 150 caracteres')
    .regex(REGEX_USUARIO, MENSAJE_USUARIO),
  password: z.string().min(1, 'Indica una contraseña').max(128, 'Máximo 128 caracteres'),
})
const schemaEditar = z.object(campos)
type Valores = z.infer<typeof schemaCrear>

function Opcion({
  id,
  titulo,
  ayuda,
  ...props
}: { id: string; titulo: string; ayuda: string } & React.ComponentProps<'input'>) {
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-0.5 size-4" {...props} />
      <label htmlFor={id} className="space-y-0.5 text-sm">
        <span className="block font-medium">{titulo}</span>
        <span className="block text-xs text-muted-foreground">{ayuda}</span>
      </label>
    </div>
  )
}

interface FormularioProps {
  usuario: Usuario | null
  /** Solo el superusuario puede dar o quitar el rol Admin (D-16). */
  puedeDarAdmin: boolean
  onCancelar: () => void
}

function FormularioUsuario({ usuario, puedeDarAdmin, onCancelar }: FormularioProps) {
  const queryClient = useQueryClient()
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const editando = usuario !== null
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(editando ? (schemaEditar as unknown as typeof schemaCrear) : schemaCrear),
    defaultValues: {
      username: usuario?.username ?? '',
      password: '',
      first_name: usuario?.first_name ?? '',
      last_name: usuario?.last_name ?? '',
      email: usuario?.email ?? '',
      is_active: usuario?.is_active ?? true,
      is_admin: usuario?.is_admin ?? false,
      is_moderator: usuario?.is_moderator ?? false,
    },
  })

  const guardar = useMutation({
    mutationFn: async (v: Valores) => {
      const comunes = {
        first_name: v.first_name,
        last_name: v.last_name,
        email: v.email || null,
        is_active: v.is_active,
        // Un Admin no puede tocar este campo: ni siquiera se envía.
        ...(puedeDarAdmin ? { is_admin: v.is_admin } : {}),
        is_moderator: v.is_moderator,
      }
      const resultado = usuario
        ? await api.PATCH('/api/users/{id}/', { params: { path: { id: usuario.id } }, body: comunes })
        : await api.POST('/api/users/', {
            body: { username: v.username, password: v.password, ...comunes },
          })
      if (!resultado.data) {
        throw new ErrorDeApi(interpretarError(resultado.response.status, resultado.error))
      }
      return resultado.data
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      onCancelar()
    },
    onError: (error) => {
      if (error instanceof ErrorDeApi) {
        let mostrado = false
        for (const campo of ['username', 'password', 'email', 'first_name', 'last_name'] as const) {
          const mensaje = error.info.campos[campo]
          if (mensaje) {
            setError(campo, { message: mensaje })
            mostrado = true
          }
        }
        if (mostrado) return
      }
      setErrorGeneral(mensajeDeError(error, 'No se pudo guardar la cuenta.'))
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((valores) => {
        setErrorGeneral(null)
        guardar.mutate(valores)
      })}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="usuario-username"
          label="Usuario"
          autoComplete="off"
          readOnly={editando}
          error={errors.username?.message}
          {...register('username')}
        />
        {!editando && (
          <FormField
            id="usuario-password"
            label="Contraseña"
            type="password"
            autoComplete="new-password"
            error={errors.password?.message}
            {...register('password')}
          />
        )}
        <FormField id="usuario-nombre" label="Nombre" error={errors.first_name?.message} {...register('first_name')} />
        <FormField
          id="usuario-apellido"
          label="Apellidos"
          error={errors.last_name?.message}
          {...register('last_name')}
        />
        <div className="sm:col-span-2">
          <FormField
            id="usuario-email"
            label="Correo (opcional)"
            type="email"
            error={errors.email?.message}
            {...register('email')}
          />
        </div>
      </div>

      <div className="space-y-3">
        <Opcion
          id="usuario-activo"
          titulo="Cuenta activa"
          ayuda="Una cuenta desactivada no puede iniciar sesión. No se borra, para conservar el historial."
          {...register('is_active')}
        />
        <Opcion
          id="usuario-moderador"
          titulo="Moderador"
          ayuda="Puede crear entidades por su cuenta y gestionar las que creó, pero solo ve esas. No administra usuarios."
          {...register('is_moderator')}
        />
        {puedeDarAdmin && (
          <Opcion
            id="usuario-admin"
            titulo="Administrador"
            ayuda="Gestiona usuarios, roles, tipos de entidad y entidades. Solo un superusuario puede darlo o quitarlo."
            {...register('is_admin')}
          />
        )}
      </div>

      {errorGeneral && (
        <p role="alert" className="text-sm text-destructive">
          {errorGeneral}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancelar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={guardar.isPending}>
          {guardar.isPending ? 'Guardando…' : editando ? 'Guardar cambios' : 'Crear cuenta'}
        </Button>
      </div>
    </form>
  )
}

interface UsuarioDialogProps {
  open: boolean
  /** La cuenta a editar, o `null` para crear una nueva. */
  usuario: Usuario | null
  puedeDarAdmin: boolean
  onClose: () => void
}

export function UsuarioDialog({ open, usuario, puedeDarAdmin, onClose }: UsuarioDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={usuario ? `Editar «${usuario.username}»` : 'Nueva cuenta'}
      description={
        usuario
          ? 'El usuario y la contraseña no se cambian desde aquí.'
          : 'La persona podrá cambiar su contraseña después de iniciar sesión.'
      }
    >
      {/* `key` reinicia el formulario al abrir otra cuenta. */}
      <FormularioUsuario
        key={usuario?.id ?? 'nuevo'}
        usuario={usuario}
        puedeDarAdmin={puedeDarAdmin}
        onCancelar={onClose}
      />
    </Dialog>
  )
}

/** Quita el bloqueo por intentos fallidos (HU-21). */
export function BotonDesbloquear({ usuario }: { usuario: Usuario }) {
  const queryClient = useQueryClient()
  const desbloquear = useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST('/api/users/{id}/unlock/', {
        params: { path: { id: usuario.id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, error))
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        aria-label={`Desbloquear a ${usuario.username}`}
        disabled={desbloquear.isPending}
        onClick={() => desbloquear.mutate()}
      >
        {desbloquear.isPending ? 'Desbloqueando…' : 'Desbloquear'}
      </Button>
      {desbloquear.isError && (
        <span role="alert" className="text-xs text-destructive">
          {mensajeDeError(desbloquear.error, 'No se pudo desbloquear.')}
        </span>
      )}
    </>
  )
}
