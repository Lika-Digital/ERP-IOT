import { useEffect, useState } from 'react'
import { getMarina } from '../api/marinas'

// one request per marina per page load, shared by the menu and the page title
const cache = new Map<number, Promise<string | null>>()

/** The marina's name, for the menu and page titles (6b: "Marina #1" said nothing). */
export function useMarinaName(id: number | null | undefined): string | null {
  const [name, setName] = useState<string | null>(null)
  useEffect(() => {
    if (!id) { setName(null); return }
    let live = true
    if (!cache.has(id)) {
      cache.set(id, getMarina(id).then((m) => m.name ?? null).catch(() => { cache.delete(id); return null }))
    }
    cache.get(id)!.then((n) => { if (live) setName(n) })
    return () => { live = false }
  }, [id])
  return name
}
