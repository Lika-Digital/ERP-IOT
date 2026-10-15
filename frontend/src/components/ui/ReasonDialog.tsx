import { useState } from 'react'
import { create } from 'zustand'

/**
 * A reason, asked in a real dialog (O38; was window.prompt). Every operator
 * command and every 2FA reset carries one — it is written to the audit before
 * anything happens, and the server refuses an action without it (spec §5.3, §7.1).
 *
 *   const reason = await askReason('Q2: turn on')   // null = cancelled
 */
interface Pending {
  what: string
  resolve: (r: string | null) => void
}

const useReasonStore = create<{ pending: Pending | null; set: (p: Pending | null) => void }>((set) => ({
  pending: null,
  set: (pending) => set({ pending }),
}))

export const MIN_REASON = 3

export function askReason(what: string): Promise<string | null> {
  return new Promise((resolve) => {
    const prev = useReasonStore.getState().pending
    if (prev) prev.resolve(null)
    useReasonStore.getState().set({ what, resolve })
  })
}

/** Mounted once, in App. */
export function ReasonDialogHost() {
  const { pending, set } = useReasonStore()
  const [text, setText] = useState('')

  if (!pending) return null
  const close = (value: string | null) => {
    pending.resolve(value)
    set(null)
    setText('')
  }
  const ok = text.trim().length >= MIN_REASON

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-reason-dialog>
      <div className="absolute inset-0 bg-black/60" onClick={() => close(null)} />
      <form
        className="relative bg-surface text-fg border border-line rounded-card shadow-card max-w-md w-full p-6 z-10 space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (ok) close(text.trim())
        }}
      >
        <h2 className="text-lg font-bold tracking-tight">A reason is required</h2>
        <p className="text-sm text-fg-muted">
          {pending.what} — the reason is written to the audit log before the command runs (at least {MIN_REASON} characters).
        </p>
        <textarea
          className="input"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
          data-reason-input
        />
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={() => close(null)}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={!ok} data-reason-ok>
            Confirm
          </button>
        </div>
      </form>
    </div>
  )
}
