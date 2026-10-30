/** Lo que devuelve DRF al fallar: `{ detail }` o `{ campo: [mensajes] }`, a veces anidado (`new_user`). */
export interface InfoError {
  status: number
  /** Mensaje que no es de un campo (`detail` o `non_field_errors`). */
  general?: string
  /** Primer mensaje por campo; los anidados usan punto (`new_user.password`). */
  campos: Record<string, string>
}

export class ErrorDeApi extends Error {
  info: InfoError

  constructor(info: InfoError) {
    super(info.general ?? 'Error de la API')
    this.info = info
  }
}

function aplanar(valor: unknown, prefijo: string, salida: Record<string, string>): void {
  if (typeof valor === 'string') {
    salida[prefijo] ??= valor
  } else if (Array.isArray(valor)) {
    for (const item of valor) aplanar(item, prefijo, salida)
  } else if (valor && typeof valor === 'object') {
    for (const [clave, item] of Object.entries(valor)) {
      aplanar(item, prefijo ? `${prefijo}.${clave}` : clave, salida)
    }
  }
}

/** Convierte el cuerpo de un error de DRF en un mensaje general y mensajes por campo. */
export function interpretarError(status: number, cuerpo: unknown): InfoError {
  const campos: Record<string, string> = {}
  aplanar(cuerpo, '', campos)
  const general = campos.detail ?? campos.non_field_errors ?? campos['']
  delete campos.detail
  delete campos.non_field_errors
  delete campos['']
  return { status, general, campos }
}

/** Texto para mostrar a la persona ante cualquier error de una petición. */
export function mensajeDeError(error: unknown, porDefecto: string): string {
  if (error instanceof ErrorDeApi) {
    return error.info.general ?? Object.values(error.info.campos)[0] ?? porDefecto
  }
  if (error instanceof TypeError) return 'No se pudo conectar con el servidor.'
  return porDefecto
}
