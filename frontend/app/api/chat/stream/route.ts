import type { NextRequest } from "next/server"

import { createClient } from "@/lib/supabase/server"

// Same-origin proxy for the chat SSE stream. The browser POSTs here (cookies ride
// along automatically), we read the access token from the SERVER session — which
// is reliable, unlike the browser client's getSession — and forward the request to
// the FastAPI backend, streaming its SSE response straight back. This keeps the
// backend behind one origin (no CORS) and avoids depending on client-side cookies.

const API_URL = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
)

export const dynamic = "force-dynamic"

export async function POST(request: NextRequest) {
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  const token = session?.access_token
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  const body = await request.text()
  const upstream = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body,
    signal: request.signal,
    // @ts-expect-error - Node/undici streaming request option, not in the DOM types.
    duplex: "half",
  })

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  })
}
