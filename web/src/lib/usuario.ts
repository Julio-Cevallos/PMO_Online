/** Nombre de usuario válido (igual que el validador de Django): letras, dígitos y @ . + - _, sin espacios. */
export const REGEX_USUARIO = /^[\w.@+-]+$/

export const MENSAJE_USUARIO = 'Solo letras, dígitos y @ . + - _ (sin espacios)'

/** Mensaje de error del nombre de usuario, o `undefined` si es válido. */
export function errorDeUsuario(valor: string): string | undefined {
  const texto = valor.trim()
  if (!texto) return 'Indica el nombre de usuario'
  if (texto.length > 150) return 'Máximo 150 caracteres'
  if (!REGEX_USUARIO.test(texto)) return MENSAJE_USUARIO
  return undefined
}
