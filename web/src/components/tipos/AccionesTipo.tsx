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
import type { TipoEntidad } from '@/lib/tipos'

const schema = z.object({
  nombre: z.string().trim().min(1, 'El nombre no puede estar vacío').max(80, 'Máximo 80 caracteres'),
  nombre_plural: z.string().trim().min(1, 'Indica el nombre en plural').max(80, 'Máximo 80 caracteres'),
  admite_tareas: z.boolean(),
  activo: z.boolean(),
})
type Valores = z.infer<typeof schema>

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

function FormularioTipo({ tipo, onCancelar }: { tipo: TipoEntidad | null; onCancelar: () => void }) {
  const queryClient = useQueryClient()
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: {
      nombre: tipo?.nombre ?? '',
      nombre_plural: tipo?.nombre_plural ?? '',
      admite_tareas: tipo?.admite_tareas ?? true,
      activo: tipo?.activo ?? true,
    },
  })

  const guardar = useMutation({
    mutationFn: async (v: Valores) => {
      const resultado = tipo
        ? await api.PATCH('/api/entity-types/{id}/', { params: { path: { id: tipo.id } }, body: v })
        : await api.POST('/api/entity-types/', { body: v })
      if (!resultado.data) {
        throw new ErrorDeApi(interpretarError(resultado.response.status, resultado.error))
      }
      return resultado.data
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['entity-types'] })
      await queryClient.invalidateQueries({ queryKey: ['entities'] })
      onCancelar()
    },
    onError: (error) => {
      if (error instanceof ErrorDeApi) {
        let mostrado = false
        for (const campo of ['nombre', 'nombre_plural'] as const) {
          const mensaje = error.info.campos[campo]
          if (mensaje) {
            setError(campo, { message: mensaje })
            mostrado = true
          }
        }
        if (mostrado) return
      }
      setErrorGeneral(mensajeDeError(error, 'No se pudo guardar el tipo.'))
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
        <FormField id="tipo-nombre" label="Nombre" error={errors.nombre?.message} {...register('nombre')} />
        <FormField
          id="tipo-plural"
          label="Nombre en plural"
          error={errors.nombre_plural?.message}
          {...register('nombre_plural')}
        />
      </div>

      <div className="space-y-3">
        <Opcion
          id="tipo-tareas"
          titulo="Admite tareas y Gantt"
          ayuda="Las entidades de este tipo podrán tener cronograma."
          {...register('admite_tareas')}
        />
        <Opcion
          id="tipo-activo"
          titulo="Activo"
          ayuda="Un tipo inactivo no se ofrece al crear entidades nuevas."
          {...register('activo')}
        />
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
          {guardar.isPending ? 'Guardando…' : tipo ? 'Guardar cambios' : 'Crear tipo'}
        </Button>
      </div>
    </form>
  )
}

interface TipoDialogProps {
  open: boolean
  /** El tipo a editar, o `null` para crear uno nuevo. */
  tipo: TipoEntidad | null
  onClose: () => void
}

export function TipoDialog({ open, tipo, onClose }: TipoDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={tipo ? `Editar «${tipo.nombre}»` : 'Nuevo tipo de entidad'}
      description="Los tipos son las categorías de entidad: proyectos, sucursales, proveedores…"
    >
      <FormularioTipo tipo={tipo} onCancelar={onClose} />
    </Dialog>
  )
}

function ConfirmarEliminar({ tipo, onClose }: { tipo: TipoEntidad; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const eliminar = useMutation({
    mutationFn: async () => {
      const { error: cuerpo, response } = await api.DELETE('/api/entity-types/{id}/', {
        params: { path: { id: tipo.id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['entity-types'] })
      onClose()
    },
    onError: (e) => setError(mensajeDeError(e, 'No se pudo eliminar el tipo.')),
  })

  return (
    <div className="space-y-4">
      <p className="text-sm">
        Se eliminará el tipo <strong>{tipo.nombre}</strong>. Esta acción no se puede deshacer. Solo
        se puede eliminar un tipo que no tenga entidades; si las tiene, desactívalo.
      </p>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button
          type="button"
          variant="destructive"
          disabled={eliminar.isPending}
          onClick={() => {
            setError(null)
            eliminar.mutate()
          }}
        >
          {eliminar.isPending ? 'Eliminando…' : 'Eliminar'}
        </Button>
      </div>
    </div>
  )
}

export function EliminarTipoDialog({ tipo, onClose }: { tipo: TipoEntidad | null; onClose: () => void }) {
  return (
    <Dialog open={tipo !== null} onClose={onClose} title="¿Eliminar tipo?">
      {tipo && <ConfirmarEliminar tipo={tipo} onClose={onClose} />}
    </Dialog>
  )
}
