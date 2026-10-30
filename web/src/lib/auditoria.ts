import type { components } from '@api-client/schema'

export type EventoAuditoria = components['schemas']['EventoAuditoria']

export interface Cambio {
  campo: string
  antes: unknown
  despues: unknown
}

/** Grupos de acciones para filtrar: el prefijo coincide con el que acepta `?accion=` del backend. */
export const GRUPOS_ACCION = [
  { prefijo: 'usuario.', etiqueta: 'Usuarios y sesiones' },
  { prefijo: 'rol.', etiqueta: 'Roles' },
  { prefijo: 'tipo.', etiqueta: 'Tipos de entidad' },
  { prefijo: 'entidad.', etiqueta: 'Entidades' },
  { prefijo: 'miembro.', etiqueta: 'Miembros' },
  { prefijo: 'invitacion.', etiqueta: 'Invitaciones' },
  { prefijo: 'portafolio.', etiqueta: 'Portafolios' },
] as const

export const CATEGORIAS = [
  { valor: 'sistema', etiqueta: 'Sistema' },
  { valor: 'entidad', etiqueta: 'Entidad' },
  { valor: 'contenido', etiqueta: 'Contenido' },
] as const

const ACCIONES: Record<string, string> = {
  'usuario.iniciar_sesion': 'Inició sesión',
  'usuario.bloquear': 'Cuenta bloqueada por intentos fallidos',
  'usuario.desbloquear': 'Cuenta desbloqueada',
  'usuario.cambiar_clave': 'Cambió su contraseña',
  'usuario.registrar': 'Se registró',
  'usuario.crear': 'Cuenta creada',
  'usuario.editar': 'Cuenta editada',
  'usuario.editar_perfil': 'Editó su perfil',
  'usuario.dar_admin': 'Rol Admin otorgado',
  'usuario.quitar_admin': 'Rol Admin retirado',
  'usuario.dar_moderador': 'Rol Moderador otorgado',
  'usuario.quitar_moderador': 'Rol Moderador retirado',
  'usuario.desactivar': 'Cuenta desactivada',
  'usuario.reactivar': 'Cuenta reactivada',
  'rol.crear': 'Rol creado',
  'rol.editar': 'Rol editado',
  'rol.eliminar': 'Rol eliminado',
  'tipo.crear': 'Tipo de entidad creado',
  'tipo.editar': 'Tipo de entidad editado',
  'tipo.eliminar': 'Tipo de entidad eliminado',
  'entidad.crear': 'Entidad creada',
  'entidad.editar': 'Entidad editada',
  'entidad.archivar': 'Entidad archivada',
  'entidad.reactivar': 'Entidad reactivada',
  'miembro.agregar': 'Miembro agregado',
  'miembro.cambiar_rol': 'Rol de miembro cambiado',
  'miembro.desactivar': 'Miembro desactivado',
  'miembro.reactivar': 'Miembro reactivado',
  'entidad.mover': 'Entidad movida de portafolio',
  'portafolio.crear': 'Portafolio creado',
  'portafolio.editar': 'Portafolio editado',
  'portafolio.eliminar': 'Portafolio eliminado',
  'portafolio.miembro_agregar': 'Miembro agregado al portafolio',
  'portafolio.miembro_cambiar_rol': 'Rol de miembro del portafolio cambiado',
  'portafolio.miembro_desactivar': 'Miembro del portafolio desactivado',
  'portafolio.miembro_reactivar': 'Miembro del portafolio reactivado',
  'portafolio.invitacion_enviar': 'Invitación al portafolio enviada',
  'portafolio.invitacion_aceptar': 'Invitación al portafolio aceptada',
  'portafolio.invitacion_rechazar': 'Invitación al portafolio rechazada',
  'portafolio.invitacion_cancelar': 'Invitación al portafolio cancelada',
  'invitacion.enviar': 'Invitación enviada',
  'invitacion.aceptar': 'Invitación aceptada',
  'invitacion.rechazar': 'Invitación rechazada',
  'invitacion.cancelar': 'Invitación cancelada',
}

const CAMPOS: Record<string, string> = {
  username: 'Usuario',
  email: 'Correo',
  first_name: 'Nombre',
  last_name: 'Apellidos',
  is_active: 'Cuenta activa',
  is_admin: 'Administrador',
  is_moderator: 'Moderador',
  password: 'Contraseña',
  nombre: 'Nombre',
  nombre_plural: 'Nombre en plural',
  admite_tareas: 'Admite tareas',
  activo: 'Activo',
  descripcion: 'Descripción',
  estado: 'Estado',
  tipo: 'Tipo',
  rol: 'Rol',
  activa: 'Membresía activa',
  nivel: 'Nivel',
  nivel_minimo_para_asignar: 'Nivel mínimo para asignar',
  permisos: 'Permisos',
  usuario: 'Usuario',
  cuenta_nueva: 'Cuenta nueva',
  al_agregar: 'Reactivado al agregar',
  intentos: 'Intentos fallidos',
  bloqueado_hasta: 'Bloqueada hasta',
  entidad: 'Entidad',
  portafolio: 'Portafolio',
  personal: 'Personal',
  desde: 'Desde',
  hacia: 'Hacia',
  al_aceptar: 'Reactivado al aceptar',
}

/** Texto en español de una acción; si es nueva y aún no está en la tabla, se muestra tal cual. */
export const etiquetaAccion = (accion: string) => ACCIONES[accion] ?? accion
export const etiquetaCampo = (campo: string) => CAMPOS[campo] ?? campo

/** Los cambios llegan como JSON libre: se aceptan solo los elementos con la forma esperada. */
export function cambiosDe(evento: Pick<EventoAuditoria, 'cambios'>): Cambio[] {
  if (!Array.isArray(evento.cambios)) return []
  return evento.cambios.filter(
    (c): c is Cambio => typeof c === 'object' && c !== null && typeof (c as Cambio).campo === 'string',
  )
}

/** Detalle del evento como pares clave-valor (usuario afectado, rol, intentos…). */
export function detalleDe(evento: Pick<EventoAuditoria, 'detalle'>): [string, string][] {
  const d = evento.detalle
  if (typeof d !== 'object' || d === null || Array.isArray(d)) return []
  return Object.entries(d).map(([clave, valor]) => [clave, formatearValor(valor)])
}

export function formatearValor(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—'
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) return valor.length ? valor.map(formatearValor).join(', ') : '—'
  if (typeof valor === 'object') return JSON.stringify(valor)
  return String(valor)
}

export const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString('es-EC', { dateStyle: 'medium', timeStyle: 'medium' })
