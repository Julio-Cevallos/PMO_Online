import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import { nombreDe, type Miembro, type RolAsignable } from '@/lib/tipos'

interface CambiarRolProps {
  miembro: Miembro | null
  entidadId: number
  roles: RolAsignable[]
  onClose: () => void
  onHecho: (miembro: Miembro) => void
}

function FormularioCambiarRol({ miembro, entidadId, roles, onClose, onHecho }: CambiarRolProps & { miembro: Miembro }) {
  const [rol, setRol] = useState(String(miembro.rol))
  const [error, setError] = useState<string | null>(null)

  const guardar = useMutation({
    mutationFn: async () => {
      const { data, error: cuerpo, response } = await api.PATCH('/api/entities/{entidad_id}/members/{id}/', {
        params: { path: { entidad_id: entidadId, id: miembro.id } },
        body: { rol: Number(rol) },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
      return data
    },
    onSuccess: onHecho,
    onError: (e) => setError(mensajeDeError(e, 'No se pudo cambiar el rol.')),
  })

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        setError(null)
        guardar.mutate()
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="cambiar-rol">Nuevo rol</Label>
        <Select id="cambiar-rol" className="w-full" value={rol} onChange={(e) => setRol(e.target.value)}>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        <p className="text-xs text-muted-foreground">Rol actual: {miembro.rol_nombre}.</p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
        <Button type="submit" disabled={guardar.isPending || rol === String(miembro.rol)}>
          {guardar.isPending ? 'Guardando…' : 'Guardar'}
        </Button>
      </div>
    </form>
  )
}

/** Cambia el rol de un miembro (solo se ofrecen los roles que quien consulta puede asignar). */
export function CambiarRolDialog(props: CambiarRolProps) {
  const { miembro, onClose } = props
  return (
    <Dialog
      open={miembro !== null}
      onClose={onClose}
      title={miembro ? `Cambiar el rol de ${nombreDe(miembro)}` : ''}
    >
      {miembro && <FormularioCambiarRol {...props} miembro={miembro} />}
    </Dialog>
  )
}

interface DesactivarProps {
  miembro: Miembro | null
  entidadId: number
  onClose: () => void
  onHecho: (miembro: Miembro) => void
}

function ConfirmarDesactivar({ miembro, entidadId, onClose, onHecho }: DesactivarProps & { miembro: Miembro }) {
  const [error, setError] = useState<string | null>(null)

  const desactivar = useMutation({
    mutationFn: async () => {
      const { error: cuerpo, response } = await api.DELETE('/api/entities/{entidad_id}/members/{id}/', {
        params: { path: { entidad_id: entidadId, id: miembro.id } },
      })
      if (!response.ok) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
    },
    onSuccess: () => onHecho(miembro),
    onError: (e) => setError(mensajeDeError(e, 'No se pudo desactivar a la persona.')),
  })

  return (
    <div className="space-y-4">
      <p className="text-sm">
        <strong>{nombreDe(miembro)}</strong> perderá el acceso a la entidad. Su cuenta no se borra y
        puedes reactivarla cuando quieras.
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
          disabled={desactivar.isPending}
          onClick={() => {
            setError(null)
            desactivar.mutate()
          }}
        >
          {desactivar.isPending ? 'Desactivando…' : 'Desactivar'}
        </Button>
      </div>
    </div>
  )
}

/** Pide confirmación antes de desactivar a un miembro. */
export function DesactivarMiembroDialog(props: DesactivarProps) {
  const { miembro, onClose } = props
  return (
    <Dialog open={miembro !== null} onClose={onClose} title="¿Desactivar miembro?">
      {miembro && <ConfirmarDesactivar {...props} miembro={miembro} />}
    </Dialog>
  )
}
