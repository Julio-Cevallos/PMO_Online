import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import { EstadoEntidad } from '@/components/entidades/EstadoEntidad'
import { MoverEntidad } from '@/components/entidades/MoverEntidad'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Entidad } from '@/lib/tipos'

const schema = z.object({
  nombre: z.string().trim().min(1, 'El nombre no puede estar vacío').max(120, 'Máximo 120 caracteres'),
  descripcion: z.string(),
})
type Valores = z.infer<typeof schema>

function Dato({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground uppercase">{titulo}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  )
}

/** Datos de la entidad. Se pueden editar (nombre y descripción) solo si el backend lo permite. */
export function DatosEntidad({ entidad }: { entidad: Entidad }) {
  const queryClient = useQueryClient()
  const [guardado, setGuardado] = useState(false)
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isDirty },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { nombre: entidad.nombre, descripcion: entidad.descripcion ?? '' },
  })

  const guardar = useMutation({
    mutationFn: async (valores: Valores) => {
      const { data, error, response } = await api.PATCH('/api/entities/{id}/', {
        params: { path: { id: entidad.id } },
        body: { nombre: valores.nombre, descripcion: valores.descripcion },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
    onSuccess: async (data) => {
      reset({ nombre: data.nombre, descripcion: data.descripcion ?? '' })
      setGuardado(true)
      await queryClient.invalidateQueries({ queryKey: ['entity', entidad.id] })
      await queryClient.invalidateQueries({ queryKey: ['entities'] })
    },
    onError: (error) => {
      if (error instanceof ErrorDeApi && error.info.campos.nombre) {
        setError('nombre', { message: error.info.campos.nombre })
        return
      }
      setErrorGeneral(mensajeDeError(error, 'No se pudieron guardar los cambios.'))
    },
  })

  const metadatos = (
    <dl className="grid max-w-xl gap-4 sm:grid-cols-3">
      <Dato titulo="Tipo">{entidad.tipo_nombre}</Dato>
      <Dato titulo="Estado">{entidad.estado === 'archivada' ? 'Archivada' : 'Activa'}</Dato>
      <Dato titulo="Portafolio">{entidad.portafolio_nombre}</Dato>
      <Dato titulo="Creada">{new Date(entidad.creado_en).toLocaleDateString('es')}</Dato>
    </dl>
  )

  if (!entidad.puede_editar) {
    return (
      <div className="space-y-6">
        <dl className="max-w-xl space-y-4">
          <Dato titulo="Nombre">{entidad.nombre}</Dato>
          <Dato titulo="Descripción">
            {entidad.descripcion || <span className="text-muted-foreground">Sin descripción</span>}
          </Dato>
        </dl>
        {metadatos}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <form
        noValidate
        className="max-w-xl space-y-4"
        onSubmit={handleSubmit((valores) => {
          setGuardado(false)
          setErrorGeneral(null)
          guardar.mutate(valores)
        })}
      >
        <FormField id="nombre" label="Nombre" error={errors.nombre?.message} {...register('nombre')} />
        <div className="space-y-1.5">
          <Label htmlFor="descripcion">Descripción</Label>
          <Textarea id="descripcion" {...register('descripcion')} />
        </div>
        {errorGeneral && (
          <p role="alert" className="text-sm text-destructive">
            {errorGeneral}
          </p>
        )}
        {guardado && !isDirty && (
          <p role="status" className="text-sm text-muted-foreground">
            Cambios guardados.
          </p>
        )}
        <Button type="submit" disabled={!isDirty || guardar.isPending}>
          {guardar.isPending ? 'Guardando…' : 'Guardar cambios'}
        </Button>
      </form>
      {metadatos}
      {entidad.puede_archivar && <EstadoEntidad entidad={entidad} />}
      {entidad.puede_mover && <MoverEntidad entidad={entidad} />}
    </div>
  )
}
