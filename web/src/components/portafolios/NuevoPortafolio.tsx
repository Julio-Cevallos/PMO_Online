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

const schema = z.object({
  nombre: z.string().trim().min(1, 'El nombre no puede estar vacío').max(120, 'Máximo 120 caracteres'),
  descripcion: z.string(),
})
type Valores = z.infer<typeof schema>

function Formulario({ onCancelar }: { onCancelar: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<Valores>({ resolver: zodResolver(schema), defaultValues: { nombre: '', descripcion: '' } })

  const crear = useMutation({
    mutationFn: async (v: Valores) => {
      const { data, error, response } = await api.POST('/api/portfolios/', { body: v })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
    onSuccess: async (portafolio) => {
      await queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      onCancelar()
      navigate(`/portfolios/${portafolio.id}`)
    },
    onError: (error) => {
      const mensaje = error instanceof ErrorDeApi ? error.info.campos.nombre : undefined
      if (mensaje) setError('nombre', { message: mensaje })
      else setErrorGeneral(mensajeDeError(error, 'No se pudo crear el portafolio.'))
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((valores) => {
        setErrorGeneral(null)
        crear.mutate(valores)
      })}
    >
      <FormField id="portafolio-nombre" label="Nombre" error={errors.nombre?.message} {...register('nombre')} />
      <div className="space-y-1.5">
        <Label htmlFor="portafolio-descripcion">Descripción (opcional)</Label>
        <Textarea id="portafolio-descripcion" {...register('descripcion')} />
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
        <Button type="submit" disabled={crear.isPending}>
          {crear.isPending ? 'Creando…' : 'Crear portafolio'}
        </Button>
      </div>
    </form>
  )
}

/** Crea un portafolio (Admin o Moderador): quien lo crea queda como su Gestor. */
export function NuevoPortafolioDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Nuevo portafolio"
      description="Agrupa entidades para que varias personas las gestionen en conjunto."
    >
      <Formulario onCancelar={onClose} />
    </Dialog>
  )
}
