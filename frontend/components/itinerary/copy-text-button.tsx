"use client"

import { Copy } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { itineraryToText } from "@/lib/itinerary-text"
import type { Itinerary } from "@/types/itinerary"

export function CopyTextButton({ itinerary }: { itinerary: Itinerary }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(itineraryToText(itinerary))
      toast.success("Itinerary copied as text")
    } catch {
      toast.error("Couldn't copy to clipboard")
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={copy}>
      <Copy className="size-3.5" />
      Copy as text
    </Button>
  )
}
