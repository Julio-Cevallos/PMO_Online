import type { components } from '@api-client/schema'

/** Tipos de la API con nombres cortos (salen del esquema generado, no se escriben a mano). */
export type Entidad = components['schemas']['Entidad']
export type TipoEntidad = components['schemas']['TipoEntidad']
export type Miembro = components['schemas']['Miembro']
export type RolAsignable = components['schemas']['RolAsignable']
export type Usuario = components['schemas']['UserAdmin']
export type Candidato = components['schemas']['Candidato']
export type Invitacion = components['schemas']['Invitacion']
export type Portafolio = components['schemas']['Portafolio']
export type PortafolioMiembro = components['schemas']['PortafolioMiembro']
export type InvitacionPortafolio = components['schemas']['InvitacionPortafolio']

/** Nombre para mostrar de una persona: nombre y apellido, o el usuario si no los tiene. */
export function nombreDeUsuario(u: Pick<Usuario, 'username' | 'first_name' | 'last_name'>): string {
  return [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username
}

/** Nombre para mostrar de un miembro: nombre y apellido, o el usuario si no los tiene. */
export function nombreDe(miembro: Miembro): string {
  return [miembro.first_name, miembro.last_name].filter(Boolean).join(' ') || miembro.username
}
