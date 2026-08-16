"use client"

import type { ChatMessage } from "@/lib/api"
import { ItineraryView } from "@/components/itinerary/itinerary-view"

import { Markdown } from "./markdown"

const TOOL_LABEL: Record<string, string> = {
  search_flights: "flights",
  search_hotels: "hotels",
  search_weather: "weather",
  search_attractions: "attractions",
  search_youtube_vlogs: "vlogs",
  google_search: "web",
}

export function MessageBubble({ message, pending }: { message: ChatMessage; pending?: boolean }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="min-w-0 max-w-full">
        {message.tools && message.tools.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {message.tools.map((t) => (
              <span key={t} className="rounded-full border px-2 py-0.5 text-[0.65rem] text-muted-foreground">
                {TOOL_LABEL[t] ?? t}
              </span>
            ))}
          </div>
        )}
        {pending && !message.content ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="size-2 animate-pulse rounded-full bg-muted-foreground/50" />
            Planning…
          </div>
        ) : (
          <Markdown>{message.content}</Markdown>
        )}
        {message.itinerary && <ItineraryView itinerary={message.itinerary} />}
      </div>
    </div>
  )
}
