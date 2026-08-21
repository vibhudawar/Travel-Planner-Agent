"use client"

import { Share2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { CopyTextButton } from "@/components/itinerary/copy-text-button"
import { Button } from "@/components/ui/button"
import type { Itinerary } from "@/types/itinerary"

// Owner-only controls under an itinerary in chat: publish a frozen public snapshot
// (returns a /i/<code> link, copied to the clipboard) and copy the plan as text.
export function ShareBar({ itinerary }: { itinerary: Itinerary }) {
  const [sharing, setSharing] = useState(false)

  async function share() {
    setSharing(true)
    try {
      const res = await fetch("/api/share", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ itinerary }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const { short_code } = (await res.json()) as { short_code: string }
      const url = `${window.location.origin}/i/${short_code}`
      await navigator.clipboard.writeText(url)
      toast.success("Public link copied", { description: url })
    } catch {
      toast.error("Couldn't create a share link. Please try again.")
    } finally {
      setSharing(false)
    }
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      <Button variant="outline" size="sm" onClick={share} disabled={sharing}>
        <Share2 className="size-3.5" />
        {sharing ? "Creating link…" : "Share"}
      </Button>
      <CopyTextButton itinerary={itinerary} />
    </div>
  )
}
