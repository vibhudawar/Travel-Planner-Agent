import { ExternalLink } from "lucide-react"

import type { Activity } from "@/types/itinerary"

import { Section } from "./shared"

export function AttractionsSection({ attractions }: { attractions: Activity[] }) {
  if (attractions.length === 0) return null

  return (
    <Section title="Attractions">
      <div className="flex flex-wrap gap-1.5">
        {attractions.map((a, i) =>
          a.link ? (
            <a
              key={i}
              href={a.link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:border-primary hover:text-primary"
            >
              {a.name}
              <ExternalLink className="size-3 shrink-0" />
            </a>
          ) : (
            <span key={i} className="rounded-md border px-2 py-1 text-xs">
              {a.name}
            </span>
          ),
        )}
      </div>
    </Section>
  )
}
