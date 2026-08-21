import type { NextRequest } from "next/server"

// Same-origin proxy for airport autocomplete → FastAPI /locations (reference data).
const API_URL = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
)

export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? ""
  const limit = request.nextUrl.searchParams.get("limit") ?? "6"
  if (!q) return Response.json({ results: [] })
  try {
    const upstream = await fetch(
      `${API_URL}/locations?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`,
      { signal: request.signal },
    )
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    })
  } catch {
    return Response.json({ results: [] }, { status: 200 })
  }
}
