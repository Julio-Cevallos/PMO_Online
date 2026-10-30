import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { api } from '@/lib/api'
import { usePortafolios } from '@/lib/consultas'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Entidad } from '@/lib/tipos'

/** Cambia la entidad de portafolio. Solo se ofrece a quien puede moverla; el destino debe permitirle crear entidades. */
export function MoverEntidad({ entidad }: { entidad: Entidad }) {
  const queryClient = useQueryClient()
  const portafolios = usePortafolios()
  const [abierto, setAbierto] = useState(false)
  const [destino, setDestino] = useState('')
  const [error, setError] = useState<string | null>(null)
  const opciones = (portafolios.data ?? []).filter(
    (p) => p.puede_crear_entidades && p.id !== entidad.portafolio,
  )

  const mover = useMutation({
    mutationFn: async () => {
      const { data, error: cuerpo, response } = await api.POST('/api/entities/{id}/move/', {
        params: { path: { id: entidad.id } },
        body: { portafolio: Number(destino) },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
      return data
    },
    onSuccess: async () => {
      setAbierto(false)
      setDestino('')
      await Promise.all(
        ['entity', 'entities', 'portfolios', 'portfolio', 'members', 'assignable-roles'].map((k) =>
          queryClient.invalidateQueries({ queryKey: [k] }),
        ),
      )
    },
    onError: (e) => setError(mensajeDeError(e, 'No se pudo mover la entidad.')),
  })

  return (
    <section aria-labelledby="mover-titulo" className="max-w-xl space-y-3 rounded-xl p-4 ring-1 ring-foreground/10">
      <div className="space-y-1">
        <h2 id="mover-titulo" className="text-sm font-semibold">
          Mover a otro portafolio
        </h2>
        <p className="text-sm text-muted-foreground">
          Hoy está en «{entidad.portafolio_nombre}». Al moverla, quienes gestionan ese portafolio dejan de verla y
          pasan a verla quienes gestionan el de destino.
        </p>
      </div>
      <Button variant="outline" disabled={opciones.length === 0} onClick={() => setAbierto(true)}>
        Mover entidad
      </Button>
      {opciones.length === 0 && !portafolios.isPending && (
        <p className="text-xs text-muted-foreground">No tienes otro portafolio donde puedas crear entidades.</p>
      )}
      <Dialog open={abierto} onClose={() => setAbierto(false)} title="Mover entidad">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (!destino) return setError('Elige un portafolio de destino.')
            setError(null)
            mover.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="mover-destino">Portafolio de destino</Label>
            <Select
              id="mover-destino"
              className="w-full"
              value={destino}
              onChange={(e) => setDestino(e.target.value)}
            >
              <option value="">Elige un portafolio</option>
              {opciones.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                  {p.personal ? ' (personal)' : ''}
                </option>
              ))}
            </Select>
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={mover.isPending}>
              {mover.isPending ? 'Moviendo…' : 'Mover'}
            </Button>
          </div>
        </form>
      </Dialog>
    </section>
  )
}
