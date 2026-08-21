"use client"

import { useRouter } from "next/navigation"
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { streamChat, type ChatMessage } from "@/lib/api"

import { Composer } from "./composer"
import { MessageBubble } from "./message-bubble"
import { TripForm } from "./trip-form"

// The chat surface (client leaf). Drives the SSE stream, keeps the URL + sidebar
// in sync when a brand-new thread is created. Keyed by conversationId at the page
// level, so switching threads mounts a fresh view with server-loaded history.
export function ChatView({
  conversationId,
  initialMessages,
}: {
  conversationId?: string
  initialMessages: ChatMessage[]
}) {
  const router = useRouter()
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [streaming, setStreaming] = useState(false)
  const convIdRef = useRef<string | undefined>(conversationId)
  const wasNew = useRef(conversationId === undefined)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  const patchLast = useCallback((patch: (m: ChatMessage) => ChatMessage) => {
    setMessages((m) => {
      const next = [...m]
      const last = next[next.length - 1]
      if (last?.role === "assistant") next[next.length - 1] = patch(last)
      return next
    })
  }, [])

  const send = useCallback(
    async (message: string) => {
      setMessages((m) => [...m, { role: "user", content: message }, { role: "assistant", content: "" }])
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      await streamChat(
        { message, conversationId: convIdRef.current, signal: controller.signal },
        {
          onConversation: (id) => {
            convIdRef.current = id
          },
          onToken: (t) => patchLast((last) => ({ ...last, content: last.content + t })),
          onTool: (tools) => patchLast((last) => ({ ...last, tools })),
          onItinerary: (itinerary) => patchLast((last) => ({ ...last, itinerary })),
          onError: (msg) => {
            toast.error(msg)
            patchLast((last) =>
              last.content ? last : { ...last, content: "_Something went wrong. Please try again._" },
            )
          },
          onDone: () => {},
        },
      ).catch((err) => {
        // Ignore user-initiated aborts (stop / unmount); surface anything else.
        if (err?.name !== "AbortError") {
          toast.error("Couldn't reach the planner. Please try again.")
          patchLast((last) =>
            last.content ? last : { ...last, content: "_Something went wrong. Please try again._" },
          )
        }
      })

      setStreaming(false)

      if (convIdRef.current) {
        if (wasNew.current) {
          wasNew.current = false
          router.replace(`/?c=${convIdRef.current}`)
        }
        router.refresh()
      }
    },
    [patchLast, router],
  )

  const stop = useCallback(() => {
    abortRef.current?.abort()
    setStreaming(false)
  }, [])

  const empty = messages.length === 0

  return (
    <div className="flex h-full flex-col">
      {empty ? (
        <div className="flex flex-1 items-center justify-center overflow-y-auto p-6">
          <div className="w-full max-w-xl text-center">
            <h1 className="text-2xl font-semibold tracking-tight">Where to next?</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Fill in your trip for a sourced, verified itinerary — flights, hotels, weather, and a
              day-by-day plan. Or just describe it below.
            </p>
            <TripForm onPlan={send} />
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div
            className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6"
            role="log"
            aria-live="polite"
            aria-label="Conversation"
          >
            {messages.map((msg, i) => (
              <MessageBubble
                key={i}
                message={msg}
                pending={streaming && i === messages.length - 1 && msg.role === "assistant"}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
      <Composer onSend={send} onStop={stop} streaming={streaming} />
    </div>
  )
}
