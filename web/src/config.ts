/**
 * Único lugar donde vive el nombre del producto en la web.
 * Para cambiarlo: define VITE_APP_NAME en web/.env o edita el valor por defecto de aquí.
 */
export const APP_NAME: string = import.meta.env.VITE_APP_NAME ?? 'PMO Online'
