import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Portafolio } from '@/lib/tipos'

const schema = z.object({
  nombre: z.string().trim().min(1, 'El nombre no puede estar vacío').max(120, 'Máximo 120 caracteres'),
  descripcion: z.string(),
})
type Valores = z.infer<typeof schema>

function EliminarPortafolio({ portafolio }: { portafolio: Portafolio }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const eliminar = useMutation({
    mutationFn: async () => {
      const { error: cuerpo, response } = await api.DELETE('/api/portfolios/{id}/', {
        params: { path: { id: portafolio.id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      navigate('/portfolios', { replace: true })
    },
    onError: (e) => setError(mensajeDeError(e, 'No se pudo eliminar el portafolio.')),
  })

  return (
    <section aria-labelledby="eliminar-pf" className="max-w-xl space-y-3 rounded-xl p-4 ring-1 ring-foreground/10">
      <h2 id="eliminar-pf" className="text-sm font-semibold">
        Eliminar portafolio
      </h2>
      <p className="text-sm text-muted-foreground">
        Solo se puede eliminar un portafolio vacío. Si tiene entidades, muévelas a otro antes.
      </p>
      <Button variant="destructive" onClick={() => setConfirmando(true)}>
        Eliminar portafolio
      </Button>
      <Dialog open={confirmando} onClose={() => setConfirmando(false)} title="¿Eliminar portafolio?">
        <div className="space-y-4">
          <p className="text-sm">
            Se eliminará <strong>{portafolio.nombre}</strong> con sus miembros e invitaciones. Esta acción no se
            puede deshacer.
          </p>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setConfirmando(false)}>
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
      </Dialog>
    </section>
  )
}

/** Datos del portafolio: se editan si el rol lo permite. */
export function DatosPortafolio({ portafolio }: { portafolio: Portafolio }) {
  const queryClient = useQueryClient()
  const [guardado, setGuardado] = useState(false)
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const editable = portafolio.puede_editar
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isDirty },
  } = useForm<Valores>({
    resolver: zodResolver(schema),
    defaultValues: { nombre: portafolio.nombre, descripcion: portafolio.descripcion ?? '' },
  })

  const guardar = useMutation({
    mutationFn: async (v: Valores) => {
      const { data, error, response } = await api.PATCH('/api/portfolios/{id}/', {
        params: { path: { id: portafolio.id } },
        body: v,
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
    onSuccess: async (nuevo) => {
      reset({ nombre: nuevo.nombre, descripcion: nuevo.descripcion ?? '' })
      setGuardado(true)
      await Promise.all(
        ['portfolio', 'portfolios', 'entities'].map((k) => queryClient.invalidateQueries({ queryKey: [k] })),
      )
    },
    onError: (error) => {
      const mensaje = error instanceof ErrorDeApi ? error.info.campos.nombre : undefined
      if (mensaje) setError('nombre', { message: mensaje })
      else setErrorGeneral(mensajeDeError(error, 'No se pudo guardar el portafolio.'))
    },
  })

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
        <FormField
          id="datos-pf-nombre"
          label="Nombre"
          readOnly={!editable || portafolio.personal}
          error={errors.nombre?.message}
          {...register('nombre')}
        />
        {portafolio.personal && (
          <p className="text-xs text-muted-foreground">
            Es tu portafolio personal: recibe las entidades que creas sin elegir otro. Sumando gente aquí, otras
            personas las gestionan contigo.
          </p>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="datos-pf-descripcion">Descripción</Label>
          <Textarea id="datos-pf-descripcion" readOnly={!editable} {...register('descripcion')} />
        </div>
        {errorGeneral && (
          <p role="alert" className="text-sm text-destructive">
            {errorGeneral}
          </p>
        )}
        {guardado && <p role="status" className="text-sm text-muted-foreground">Cambios guardados.</p>}
        {editable && (
          <Button type="submit" disabled={!isDirty || guardar.isPending}>
            {guardar.isPending ? 'Guardando…' : 'Guardar cambios'}
          </Button>
        )}
      </form>
      {portafolio.puede_eliminar && <EliminarPortafolio portafolio={portafolio} />}
    </div>
  )
}
