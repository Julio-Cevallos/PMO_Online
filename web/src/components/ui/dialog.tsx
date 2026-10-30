import { useEffect, useId, useRef, type ReactNode } from "react"

interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
}

/**
 * Ventana modal con el elemento nativo `<dialog>`: el navegador se encarga del foco, de Esc y
 * del fondo. El contenido solo existe mientras está abierta, así los formularios empiezan vacíos.
 */
function Dialog({ open, onClose, title, description, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        // Un clic en el fondo oscurecido llega al propio <dialog>.
        if (e.target === ref.current) onClose()
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-xl bg-card p-0 text-card-foreground ring-1 ring-foreground/10 backdrop:bg-black/40"
    >
      {open && (
        <div className="space-y-4 p-5">
          <div className="space-y-1">
            <h2 id={titleId} className="text-lg font-semibold tracking-tight">
              {title}
            </h2>
            {description && <p className="text-sm text-muted-foreground">{description}</p>}
          </div>
          {children}
        </div>
      )}
    </dialog>
  )
}

export { Dialog }
