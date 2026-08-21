"use client"

import { useSyncExternalStore } from "react"

const noop = () => () => {}

// Renders the "as of" timestamp in the user's local locale/timezone. Formatting a
// date during SSR causes a hydration mismatch (server locale/TZ differs from the
// browser), so useSyncExternalStore returns null on the server + initial hydration
// render (matching), then swaps in the client-formatted value — no mismatch, and
// no setState-in-effect.
export function AsOf({ iso }: { iso: string }) {
  const text = useSyncExternalStore(
    noop,
    () => new Date(iso).toLocaleString(),
    () => null,
  )
  if (!text) return null
  return <span className="text-[0.65rem] text-muted-foreground">as of {text}</span>
}
