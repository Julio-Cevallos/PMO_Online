import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useMutation } from '@tanstack/react-query'
import { BuscadorCuenta } from '@/components/entidades/BuscadorCuenta'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Invitacion, Miembro, RolAsignable } from '@/lib/tipos'
import { errorDeUsuario } from '@/lib/usuario'

type Modo = 'existente' | 'nueva'

/** Una cuenta nueva entra como miembro; una existente recibe una invitación que debe aceptar (D-27). */
export type ResultadoAlta =
  | { tipo: 'miembro'; miembro: Miembro }
  | { tipo: 'invitacion'; invitacion: Invitacion }

interface Valores {
  username: string
  rol: string
  password: string
  confirmPassword: string
  email: string
  first_name: string
  last_name: string
}

/** Campo de la API (a veces anidado en `new_user`) → campo del formulario. */
const CAMPO_DEL_FORMULARIO: Record<string, keyof Valores> = {
  username: 'username',
  rol: 'rol',
  'new_user.username': 'username',
  'new_user.password': 'password',
  'new_user.email': 'email',
  'new_user.first_name': 'first_name',
  'new_user.last_name': 'last_name',
}

function validar(v: Valores, modo: Modo): Partial<Record<keyof Valores, string>> {
  const errores: Partial<Record<keyof Valores, string>> = {}
  if (!v.rol) errores.rol = 'Elige un rol'
  if (modo === 'existente') {
    // No se valida el formato: el servidor comprueba que la cuenta exista.
    if (!v.username.trim()) errores.username = 'Indica el nombre de usuario'
  } else {
    const mensaje = errorDeUsuario(v.username)
    if (mensaje) errores.username = mensaje
  }
  if (modo === 'nueva') {
    if (v.password.length < 8) errores.password = 'Mínimo 8 caracteres'
    else if (v.password !== v.confirmPassword) errores.confirmPassword = 'Las contraseñas no coinciden'
    if (v.email && !/^\S+@\S+\.\S+$/.test(v.email)) errores.email = 'Ingresa un correo válido'
  }
  return errores
}

interface FormularioProps {
  entidadId: number
  roles: RolAsignable[]
  onCancelar: () => void
  onAgregado: (resultado: ResultadoAlta) => void
}

function FormularioAgregar({ entidadId, roles, onCancelar, onAgregado }: FormularioProps) {
  const [modo, setModo] = useState<Modo>('existente')
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    setError,
    clearErrors,
    formState: { errors },
  } = useForm<Valores>({
    defaultValues: {
      username: '',
      rol: '',
      password: '',
      confirmPassword: '',
      email: '',
      first_name: '',
      last_name: '',
    },
  })

  const agregar = useMutation({
    mutationFn: async (v: Valores) => {
      const rol = Number(v.rol)
      const username = v.username.trim()
      if (modo === 'existente') {
        const { data, error, response } = await api.POST('/api/entities/{entidad_id}/invitations/', {
          params: { path: { entidad_id: entidadId } },
          body: { username, rol },
        })
        if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
        return { tipo: 'invitacion', invitacion: data } satisfies ResultadoAlta
      }
      const { data, error, response } = await api.POST('/api/entities/{entidad_id}/members/', {
        params: { path: { entidad_id: entidadId } },
        body: {
          rol,
          new_user: {
            username,
            password: v.password,
            ...(v.email ? { email: v.email } : {}),
            ...(v.first_name ? { first_name: v.first_name } : {}),
            ...(v.last_name ? { last_name: v.last_name } : {}),
          },
        },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return { tipo: 'miembro', miembro: data } satisfies ResultadoAlta
    },
    onSuccess: onAgregado,
    onError: (error) => {
      if (error instanceof ErrorDeApi) {
        if (error.info.status === 404 && modo === 'existente') {
          setError('username', { message: 'No existe ninguna cuenta con ese nombre de usuario.' })
          return
        }
        let mostrado = false
        for (const [campo, mensaje] of Object.entries(error.info.campos)) {
          const destino = CAMPO_DEL_FORMULARIO[campo]
          if (destino) {
            setError(destino, { message: mensaje })
            mostrado = true
          }
        }
        if (mostrado) return
      }
      setErrorGeneral(mensajeDeError(error, 'No se pudo agregar a la persona.'))
    },
  })

  function cambiarModo(nuevo: Modo) {
    setModo(nuevo)
    clearErrors()
    setErrorGeneral(null)
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((valores) => {
        setErrorGeneral(null)
        const errores = validar(valores, modo)
        const campos = Object.keys(errores) as (keyof Valores)[]
        if (campos.length > 0) {
          for (const campo of campos) setError(campo, { message: errores[campo] })
          return
        }
        agregar.mutate(valores)
      })}
    >
      <div className="grid grid-cols-2 gap-2" role="group" aria-label="Tipo de alta">
        <Button
          type="button"
          variant={modo === 'existente' ? 'default' : 'outline'}
          aria-pressed={modo === 'existente'}
          onClick={() => cambiarModo('existente')}
        >
          Cuenta existente
        </Button>
        <Button
          type="button"
          variant={modo === 'nueva' ? 'default' : 'outline'}
          aria-pressed={modo === 'nueva'}
          onClick={() => cambiarModo('nueva')}
        >
          Cuenta nueva
        </Button>
      </div>

      {modo === 'existente' ? (
        <div className="space-y-2">
          <BuscadorCuenta
            entidadId={entidadId}
            value={watch('username')}
            onChange={(texto) => {
              setValue('username', texto)
              clearErrors('username')
            }}
            error={errors.username?.message}
          />
          <p className="text-xs text-muted-foreground">
            Se le enviará una invitación: la persona decide si la acepta o la rechaza.
          </p>
        </div>
      ) : (
        <FormField
          id="miembro-username"
          label="Nombre de usuario"
          autoComplete="off"
          error={errors.username?.message}
          {...register('username')}
        />
      )}

      {modo === 'nueva' && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              id="miembro-nombre"
              label="Nombre (opcional)"
              autoComplete="off"
              error={errors.first_name?.message}
              {...register('first_name')}
            />
            <FormField
              id="miembro-apellido"
              label="Apellido (opcional)"
              autoComplete="off"
              error={errors.last_name?.message}
              {...register('last_name')}
            />
          </div>
          <FormField
            id="miembro-email"
            label="Correo (opcional)"
            type="email"
            autoComplete="off"
            error={errors.email?.message}
            {...register('email')}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField
              id="miembro-password"
              label="Contraseña"
              type="password"
              autoComplete="new-password"
              error={errors.password?.message}
              {...register('password')}
            />
            <FormField
              id="miembro-confirmar"
              label="Repetir contraseña"
              type="password"
              autoComplete="new-password"
              error={errors.confirmPassword?.message}
              {...register('confirmPassword')}
            />
          </div>
        </>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="miembro-rol">Rol en la entidad</Label>
        <Select
          id="miembro-rol"
          className="w-full"
          aria-invalid={errors.rol ? true : undefined}
          {...register('rol')}
        >
          <option value="">Elige un rol</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        {errors.rol && <p className="text-sm text-destructive">{errors.rol.message}</p>}
        {roles.length === 0 && (
          <p className="text-sm text-muted-foreground">No hay roles que puedas asignar.</p>
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
        <Button type="submit" disabled={agregar.isPending}>
          {agregar.isPending
            ? modo === 'existente'
              ? 'Invitando…'
              : 'Agregando…'
            : modo === 'existente'
              ? 'Invitar'
              : 'Agregar'}
        </Button>
      </div>
    </form>
  )
}

interface Props {
  open: boolean
  entidadId: number
  roles: RolAsignable[]
  onClose: () => void
  onAgregado: (resultado: ResultadoAlta) => void
}

/** Suma a una persona a la entidad: invita a una cuenta que ya existe o crea una cuenta nueva. */
export function AgregarMiembroDialog({ open, entidadId, roles, onClose, onAgregado }: Props) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Agregar miembro"
      description="El rol que elijas debe ser de un nivel menor al tuyo."
    >
      <FormularioAgregar entidadId={entidadId} roles={roles} onCancelar={onClose} onAgregado={onAgregado} />
    </Dialog>
  )
}
