import type { HotelOption } from "@/types/itinerary"

import { LinkOut, renderPrice, Section, SourceChip } from "./shared"

export function HotelsSection({
  hotels,
  homeCurrency,
  rate,
}: {
  hotels: HotelOption[]
  homeCurrency: string | null | undefined
  rate: number | null | undefined
}) {
  if (hotels.length === 0) return null

  return (
    <Section title="Hotels">
      {hotels.map((h, i) => (
        <div key={i} className="flex items-center justify-between gap-2">
          <span>
            <LinkOut href={h.link}>{h.name}</LinkOut>
            {h.rating ? ` · ${h.rating}★` : ""}
          </span>
          <span className="flex items-center gap-2">
            <span className="tabular-nums">
              {renderPrice(h.price_per_night, homeCurrency, rate, h.price_per_night != null ? "/night" : "")}
            </span>
            <SourceChip tool={h.source_tool} />
          </span>
        </div>
      ))}
    </Section>
  )
}
