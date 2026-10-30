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
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Portafolio, TipoEntidad } from '@/lib/tipos'

const schema = z.object({
  tipo: z.string().min(1, 'Elige un tipo'),
  nombre: z.string().trim().min(1, 'El nombre no puede estar vacío').max(120, 'Máximo 120 caracteres'),
  descripcion: z.string(),
  portafolio: z.string(),
})
type Valores = z.infer<typeof schema>

interface FormularioProps {
  tipos: TipoEntidad[]
  /** Portafolios donde se puede crear (sin el personal propio, que se elige con «vacío»). */
  portafolios: Portafolio[]
  /** Si se indica, la entidad se crea en ese portafolio y no se muestra el selector. */
  portafolioFijo?: number
  /** Admin y Moderador pueden crear en su portafolio personal, sin elegir. */
  permitePersonal: boolean
  onCancelar: () => void
}

function FormularioNueva({ tipos, portafolios, portafolioFijo, permitePersonal, onCancelar }: FormularioProps) {
  const navigate = useNavigate()
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
      tipo: '',
      nombre: '',
      descripcion: '',
      portafolio: portafolioFijo ? String(portafolioFijo) : permitePersonal ? '' : String(portafolios[0]?.id ?? ''),
    },
  })

  const crear = useMutation({
    mutationFn: async (v: Valores) => {
      const { data, error, response } = await api.POST('/api/entities/', {
        body: {
          tipo: Number(v.tipo),
          nombre: v.nombre,
          descripcion: v.descripcion,
          ...(v.portafolio ? { portafolio: Number(v.portafolio) } : {}),
        },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, error))
      return data
    },
    onSuccess: async (entidad) => {
      await queryClient.invalidateQueries({ queryKey: ['entities'] })
      await queryClient.invalidateQueries({ queryKey: ['entity-types'] })
      onCancelar()
      // Se abre la entidad nueva: lo siguiente es agregarle a su responsable.
      navigate(`/entities/${entidad.id}?pestana=miembros`)
    },
    onError: (error) => {
      if (error instanceof ErrorDeApi) {
        let mostrado = false
        for (const campo of ['tipo', 'nombre', 'portafolio'] as const) {
          const mensaje = error.info.campos[campo]
          if (mensaje) {
            setError(campo, { message: mensaje })
            mostrado = true
          }
        }
        if (mostrado) return
      }
      setErrorGeneral(mensajeDeError(error, 'No se pudo crear la entidad.'))
    },
  })

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((valores) => {
        setErrorGeneral(null)
        if (!permitePersonal && !valores.portafolio) {
          setError('portafolio', { message: 'Elige un portafolio' })
          return
        }
        crear.mutate(valores)
      })}
    >
      {portafolioFijo === undefined && (
        <div className="space-y-1.5">
          <Label htmlFor="nueva-portafolio">Portafolio</Label>
          <Select
            id="nueva-portafolio"
            className="w-full"
            aria-invalid={errors.portafolio ? true : undefined}
            {...register('portafolio')}
          >
            {permitePersonal && <option value="">Mi portafolio personal («Mis entidades»)</option>}
            {!permitePersonal && <option value="">Elige un portafolio</option>}
            {portafolios.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
                {p.personal ? ' (personal)' : ''}
              </option>
            ))}
          </Select>
          {errors.portafolio && <p className="text-sm text-destructive">{errors.portafolio.message}</p>}
          <p className="text-xs text-muted-foreground">
            El portafolio decide quién gestiona la entidad. Puedes moverla a otro después.
          </p>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="nueva-tipo">Tipo</Label>
        <Select
          id="nueva-tipo"
          className="w-full"
          aria-invalid={errors.tipo ? true : undefined}
          {...register('tipo')}
        >
          <option value="">Elige un tipo</option>
          {tipos.map((t) => (
            <option key={t.id} value={t.id}>
              {t.nombre}
            </option>
          ))}
        </Select>
        {errors.tipo && <p className="text-sm text-destructive">{errors.tipo.message}</p>}
        {tipos.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No hay tipos activos. Crea o activa uno en «Tipos de entidad».
          </p>
        )}
        <p className="text-xs text-muted-foreground">El tipo no se puede cambiar después.</p>
      </div>

      <FormField id="nueva-nombre" label="Nombre" error={errors.nombre?.message} {...register('nombre')} />

      <div className="space-y-1.5">
        <Label htmlFor="nueva-descripcion">Descripción (opcional)</Label>
        <Textarea id="nueva-descripcion" {...register('descripcion')} />
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
          {crear.isPending ? 'Creando…' : 'Crear entidad'}
        </Button>
      </div>
    </form>
  )
}

interface Props {
  open: boolean
  tipos: TipoEntidad[]
  portafolios: Portafolio[]
  portafolioFijo?: number
  permitePersonal: boolean
  onClose: () => void
}

/** Crea una entidad en un portafolio. Al terminar abre su pestaña de miembros. */
export function NuevaEntidadDialog({ open, tipos, portafolios, portafolioFijo, permitePersonal, onClose }: Props) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Nueva entidad"
      description="Un proyecto, una sucursal o cualquier otro tipo que hayas definido."
    >
      {open && (
        <FormularioNueva
          tipos={tipos}
          portafolios={portafolios}
          portafolioFijo={portafolioFijo}
          permitePersonal={permitePersonal}
          onCancelar={onClose}
        />
      )}
    </Dialog>
  )
}
