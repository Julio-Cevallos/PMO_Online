import { useEffect, useId, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { LIMITE_CANDIDATOS, useCandidatos } from '@/lib/consultas'
import { mensajeDeError } from '@/lib/errores'
import { nombreDeUsuario } from '@/lib/tipos'

interface Props {
  entidadId: number
  /** Lo que hay escrito: es el nombre de usuario que se enviará, se haya elegido de la lista o no. */
  value: string
  onChange: (valor: string) => void
  error?: string
}

/** Texto con retraso, para no consultar al servidor en cada tecla. */
function useRetrasado(valor: string, ms = 250) {
  const [retrasado, setRetrasado] = useState(valor)
  useEffect(() => {
    const t = setTimeout(() => setRetrasado(valor), ms)
    return () => clearTimeout(t)
  }, [valor, ms])
  return retrasado
}

/**
 * Campo de nombre de usuario con lista de sugerencias (patrón ARIA «combobox»). La lista es solo una
 * ayuda: se puede escribir cualquier usuario y el servidor comprueba que exista al enviar. Las
 * sugerencias las decide el servidor según quién busca y son como máximo `LIMITE_CANDIDATOS`.
 */
export function BuscadorCuenta({ entidadId, value, onChange, error }: Props) {
  const id = useId()
  const listaId = `${id}-lista`
  const [abierto, setAbierto] = useState(false)
  const [activo, setActivo] = useState(0)
  // Solo cuando la persona se mueve con las flechas, Enter elige de la lista; si no, envía lo escrito.
  const [navegado, setNavegado] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)
  const texto = value.trim()
  const consulta = useCandidatos(entidadId, useRetrasado(texto), abierto)
  const opciones = consulta.data ?? []
  const hayActiva = abierto && navegado && opciones[activo] !== undefined

  useEffect(() => {
    const cerrarAlFuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false)
    }
    document.addEventListener('mousedown', cerrarAlFuera)
    return () => document.removeEventListener('mousedown', cerrarAlFuera)
  }, [])

  function alTeclear(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setAbierto(true)
      setNavegado(true)
      setActivo((i) => Math.min(navegado ? i + 1 : 0, opciones.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setNavegado(true)
      setActivo((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && hayActiva) {
      e.preventDefault()
      onChange(opciones[activo].username)
      setAbierto(false)
      setNavegado(false)
    } else if (e.key === 'Escape' && abierto) {
      e.stopPropagation() // no cierra el diálogo, solo la lista
      setAbierto(false)
    }
  }

  return (
    <div ref={contenedor} className="space-y-1.5">
      <Label htmlFor={`${id}-entrada`}>Nombre de usuario</Label>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id={`${id}-entrada`}
          role="combobox"
          aria-expanded={abierto}
          aria-controls={listaId}
          aria-autocomplete="list"
          aria-activedescendant={hayActiva ? `${id}-op-${opciones[activo].id}` : undefined}
          aria-invalid={error ? true : undefined}
          autoComplete="off"
          placeholder="Escribe o busca un usuario o nombre"
          className="pl-8"
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            setAbierto(true)
            setActivo(0)
            setNavegado(false)
          }}
          onFocus={() => setAbierto(true)}
          onKeyDown={alTeclear}
        />
        {abierto && (
          <ul
            id={listaId}
            role="listbox"
            aria-label="Sugerencias de cuentas"
            className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10"
          >
            {consulta.isError && (
              <li role="presentation" className="px-2 py-2 text-sm text-muted-foreground">
                {mensajeDeError(consulta.error, 'No se pudo buscar.')} Aun así puedes escribir el usuario.
              </li>
            )}
            {consulta.isPending && !consulta.isError && (
              <li role="presentation" className="px-2 py-2 text-sm text-muted-foreground">
                Buscando…
              </li>
            )}
            {consulta.data && opciones.length === 0 && (
              <li role="presentation" className="px-2 py-2 text-sm text-muted-foreground">
                {texto
                  ? 'Sin sugerencias. Si escribes el usuario completo, se comprobará al enviar.'
                  : 'Sin sugerencias por ahora. Puedes escribir el usuario.'}
              </li>
            )}
            {opciones.map((c, i) => (
              <li
                key={c.id}
                id={`${id}-op-${c.id}`}
                role="option"
                aria-selected={navegado && i === activo}
                onMouseEnter={() => setActivo(i)}
                onMouseDown={(e) => {
                  e.preventDefault() // evita que el campo pierda el foco antes del clic
                  onChange(c.username)
                  setAbierto(false)
                }}
                className={'cursor-pointer rounded-md px-2 py-1.5 text-sm ' + (i === activo ? 'bg-muted' : '')}
              >
                <span className="font-medium">{nombreDeUsuario(c)}</span>{' '}
                <span className="text-muted-foreground">@{c.username}</span>
              </li>
            ))}
            {opciones.length >= LIMITE_CANDIDATOS && (
              <li role="presentation" className="px-2 py-1.5 text-xs text-muted-foreground">
                Se muestran {LIMITE_CANDIDATOS} sugerencias: escribe más para acotar.
              </li>
            )}
          </ul>
        )}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}
