import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"

import { CopyTextButton } from "@/components/itinerary/copy-text-button"
import { ItineraryView } from "@/components/itinerary/itinerary-view"
import type { Itinerary } from "@/types/itinerary"

const API_URL = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
)

// Frozen snapshots are immutable — cache the page for an hour (ISR).
export const revalidate = 3600

type Shared = { itinerary: Itinerary; destination: string | null; created_at: string }

async function getShared(shortCode: string): Promise<Shared | null> {
  try {
    const res = await fetch(`${API_URL}/shared/${encodeURIComponent(shortCode)}`, {
      next: { revalidate: 3600 },
    })
    if (!res.ok) return null
    return (await res.json()) as Shared
  } catch {
    return null
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ shortCode: string }>
}): Promise<Metadata> {
  const { shortCode } = await params
  const data = await getShared(shortCode)
  if (!data) return { title: "Itinerary not found · Trip Planner" }
  const dest = data.destination ?? data.itinerary.destination
  const dates = [data.itinerary.start_date, data.itinerary.end_date].filter(Boolean).join(" → ")
  const title = `Trip to ${dest} · Trip Planner`
  const description = dates
    ? `A ${dates} itinerary — flights, hotels, weather, and a day-by-day plan.`
    : "A sourced, verified travel itinerary."
  return {
    title,
    description,
    openGraph: { title, description, type: "website" },
    twitter: { card: "summary", title, description },
  }
}

export default async function SharedItineraryPage({
  params,
}: {
  params: Promise<{ shortCode: string }>
}) {
  const { shortCode } = await params
  const data = await getShared(shortCode)
  if (!data) notFound()

  return (
    <main className="mx-auto min-h-dvh w-full max-w-3xl px-4 py-8">
      <header className="mb-4 flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">Trip Planner</p>
          <p className="text-xs text-muted-foreground">Shared itinerary · read-only</p>
        </div>
        <CopyTextButton itinerary={data.itinerary} />
      </header>
      <ItineraryView itinerary={data.itinerary} />
      <footer className="mt-6 text-center text-xs text-muted-foreground">
        <Link href="/" className="text-primary hover:underline">
          Plan your own trip →
        </Link>
      </footer>
    </main>
  )
}
