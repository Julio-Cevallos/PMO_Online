import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { ErrorDeApi, interpretarError, mensajeDeError } from '@/lib/errores'
import type { Entidad } from '@/lib/tipos'

/** Archivar o reactivar una entidad. Solo el Admin; el backend lo exige y esto solo lo ofrece a quien puede. */
export function EstadoEntidad({ entidad }: { entidad: Entidad }) {
  const queryClient = useQueryClient()
  const archivada = entidad.estado === 'archivada'
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cambiar = useMutation({
    mutationFn: async () => {
      const { data, error: cuerpo, response } = await api.PATCH('/api/entities/{id}/', {
        params: { path: { id: entidad.id } },
        body: { estado: archivada ? 'activa' : 'archivada' },
      })
      if (!data) throw new ErrorDeApi(interpretarError(response.status, cuerpo))
      return data
    },
    onSuccess: async () => {
      setConfirmando(false)
      await Promise.all(
        ['entity', 'entities', 'members', 'assignable-roles'].map((clave) =>
          queryClient.invalidateQueries({ queryKey: [clave] }),
        ),
      )
    },
    onError: (e) => setError(mensajeDeError(e, 'No se pudo cambiar el estado de la entidad.')),
  })

  return (
    <section aria-labelledby="estado-titulo" className="max-w-xl space-y-3 rounded-xl p-4 ring-1 ring-foreground/10">
      <div className="space-y-1">
        <h2 id="estado-titulo" className="text-sm font-semibold">
          {archivada ? 'Entidad archivada' : 'Archivar entidad'}
        </h2>
        <p className="text-sm text-muted-foreground">
          {archivada
            ? 'Está en solo lectura: no se pueden agregar ni modificar miembros. Reactívala para volver a trabajar con ella.'
            : 'Una entidad archivada queda en solo lectura: nadie podrá agregar ni modificar sus miembros. No se borra nada y puedes reactivarla cuando quieras.'}
        </p>
      </div>

      {error && !confirmando && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {archivada ? (
        <Button
          variant="outline"
          disabled={cambiar.isPending}
          onClick={() => {
            setError(null)
            cambiar.mutate()
          }}
        >
          {cambiar.isPending ? 'Reactivando…' : 'Reactivar entidad'}
        </Button>
      ) : (
        <Button
          variant="destructive"
          onClick={() => {
            setError(null)
            setConfirmando(true)
          }}
        >
          Archivar entidad
        </Button>
      )}

      <Dialog
        open={confirmando}
        onClose={() => setConfirmando(false)}
        title="¿Archivar esta entidad?"
        description={entidad.nombre}
      >
        <p className="text-sm">
          Quedará en solo lectura y no se podrán agregar ni modificar miembros mientras esté archivada.
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
            disabled={cambiar.isPending}
            onClick={() => {
              setError(null)
              cambiar.mutate()
            }}
          >
            {cambiar.isPending ? 'Archivando…' : 'Archivar'}
          </Button>
        </div>
      </Dialog>
    </section>
  )
}
