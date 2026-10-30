import { CambiarRolDialog, DesactivarMiembroDialog } from '@/components/entidades/AccionesMiembro'
import { AgregarMiembroDialog } from '@/components/entidades/AgregarMiembro'
import { nombreDe, type Miembro, type RolAsignable } from '@/lib/tipos'

interface Props {
  entidadId: number
  roles: RolAsignable[]
  agregando: boolean
  cambiando: Miembro | null
  desactivando: Miembro | null
  onCerrar: () => void
  /** Se llama al terminar una acción con el mensaje que se muestra a la persona. */
  onAviso: (texto: string) => void
}

/** Las tres ventanas de acciones sobre miembros, juntas para que el panel quede legible. */
export function AccionesMiembroDialogs({
  entidadId,
  roles,
  agregando,
  cambiando,
  desactivando,
  onCerrar,
  onAviso,
}: Props) {
  return (
    <>
      <AgregarMiembroDialog
        open={agregando}
        entidadId={entidadId}
        roles={roles}
        onClose={onCerrar}
        onAgregado={(r) => {
          onCerrar()
          onAviso(
            r.tipo === 'miembro'
              ? `Se agregó a ${nombreDe(r.miembro)} como ${r.miembro.rol_nombre}.`
              : `Se invitó a @${r.invitacion.username} como ${r.invitacion.rol_nombre}. Entrará cuando acepte la invitación.`,
          )
        }}
      />
      <CambiarRolDialog
        miembro={cambiando}
        entidadId={entidadId}
        roles={roles}
        onClose={onCerrar}
        onHecho={(m) => {
          onCerrar()
          onAviso(`${nombreDe(m)} ahora tiene el rol ${m.rol_nombre}.`)
        }}
      />
      <DesactivarMiembroDialog
        miembro={desactivando}
        entidadId={entidadId}
        onClose={onCerrar}
        onHecho={(m) => {
          onCerrar()
          onAviso(`Se desactivó a ${nombreDe(m)}.`)
        }}
      />
    </>
  )
}
