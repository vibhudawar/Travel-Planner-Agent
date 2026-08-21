// The single typed client for the FastAPI backend. Every call carries the
// Supabase access token as a Bearer header; the backend derives identity from it.

import type { Itinerary } from "@/types/itinerary"

// Server-side calls (getConversation/listConversations from Server Components) and
// the proxy routes must resolve the SAME backend. Prefer the server-only API_URL
// (matches app/api/*/route.ts), then NEXT_PUBLIC_API_URL, then local dev.
const API_URL =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type ChatMessage = {
  role: "user" | "assistant"
  content: string
  tools?: string[]
  itinerary?: Itinerary | null
}

export type ConversationSummary = {
  id: string
  title: string | null
  updated_at: string
}

function baseUrl(): string {
  return API_URL.replace(/\/$/, "")
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

export async function listConversations(token: string): Promise<ConversationSummary[]> {
  const res = await fetch(`${baseUrl()}/conversations`, {
    headers: authHeaders(token),
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`listConversations: ${res.status}`)
  const data = (await res.json()) as { conversations: ConversationSummary[] }
  return data.conversations ?? []
}

export async function getConversation(id: string, token: string): Promise<ChatMessage[] | null> {
  const res = await fetch(`${baseUrl()}/conversations/${id}`, {
    headers: authHeaders(token),
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`getConversation: ${res.status}`)
  const data = (await res.json()) as { messages: ChatMessage[]; itinerary: Itinerary | null }
  const messages = data.messages ?? []
  // Attach the persisted itinerary to the last assistant turn.
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      messages[i] = { ...messages[i], itinerary: data.itinerary }
      break
    }
  }
  return messages
}

export type StreamCallbacks = {
  onConversation?: (conversationId: string) => void
  onToken?: (token: string) => void
  onTool?: (tools: string[]) => void
  onItinerary?: (itinerary: Itinerary) => void
  onDone?: () => void
  onError?: (message: string) => void
}

export async function streamChat(
  params: { message: string; conversationId?: string; signal?: AbortSignal },
  cb: StreamCallbacks,
): Promise<void> {
  // Same-origin proxy (app/api/chat/stream) injects the auth token server-side and
  // forwards to the backend — no client token, no CORS.
  const res = await fetch(`/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: params.message, conversation_id: params.conversationId ?? null }),
    signal: params.signal,
  })
  if (!res.ok || !res.body) {
    cb.onError?.(`stream failed (${res.status})`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  const dispatch = (frame: string) => {
    let event = "message"
    const dataLines: string[] = []
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim())
    }
    if (dataLines.length === 0) return
    let data: unknown
    try {
      data = JSON.parse(dataLines.join("\n"))
    } catch {
      return
    }
    switch (event) {
      case "conversation":
        cb.onConversation?.((data as { conversation_id: string }).conversation_id)
        break
      case "token":
        cb.onToken?.(data as string)
        break
      case "tool":
        cb.onTool?.(data as string[])
        break
      case "itinerary":
        cb.onItinerary?.(data as Itinerary)
        break
      case "done":
        cb.onDone?.()
        break
      case "error":
        cb.onError?.(typeof data === "string" ? data : "stream error")
        break
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (frame.trim()) dispatch(frame)
    }
  }
  if (buffer.trim()) dispatch(buffer)
}
