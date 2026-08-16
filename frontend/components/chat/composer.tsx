"use client"

import { ArrowUp, Square } from "lucide-react"
import { useRef, useState } from "react"

import { Button } from "@/components/ui/button"

// Enter sends; Shift+Enter inserts a newline. Auto-grows up to a cap. While a
// response streams, the send button becomes a stop button.
export function Composer({
  onSend,
  onStop,
  streaming,
}: {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
}) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  function grow() {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  function submit() {
    const text = value.trim()
    if (!text || streaming) return
    onSend(text)
    setValue("")
    if (ref.current) ref.current.style.height = "auto"
  }

  return (
    <div className="bg-background p-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            grow()
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          rows={1}
          aria-label="Message"
          placeholder="Where do you want to go?"
          className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        {streaming ? (
          <Button size="icon" variant="secondary" onClick={onStop} aria-label="Stop">
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={submit}
            disabled={!value.trim()}
            aria-label="Send"
            className="rounded-full"
          >
            <ArrowUp className="size-4" />
          </Button>
        )}
      </div>
      <p className="mt-1.5 text-center text-[0.7rem] text-muted-foreground">
        Prices and availability are as-of retrieval — reverify before booking.
      </p>
    </div>
  )
}
