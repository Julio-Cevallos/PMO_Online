import type { ComponentProps } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface Props extends ComponentProps<typeof Input> {
  label: string
  error?: string
}

export function FormField({ label, error, id, ...inputProps }: Props) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} aria-invalid={error ? true : undefined} {...inputProps} />
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}
