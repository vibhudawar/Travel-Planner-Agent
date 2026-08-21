import type { NextRequest } from "next/server"

import { createClient } from "@/lib/supabase/server"

// Same-origin proxy: the browser POSTs the itinerary here, we inject the server
// session token and forward to the backend /share (which freezes it and returns a
// short code). No client token, no CORS.
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
    return Response.json({ detail: "Not authenticated" }, { status: 401 })
  }

  const body = await request.text()
  const upstream = await fetch(`${API_URL}/share`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body,
  })
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
