import type { FlightOption } from "@/types/itinerary"

import { LinkOut, renderPrice, Section, SourceChip } from "./shared"

export function FlightsSection({
  flights,
  homeCurrency,
  rate,
}: {
  flights: FlightOption[]
  homeCurrency: string | null | undefined
  rate: number | null | undefined
}) {
  if (flights.length === 0) return null

  return (
    <Section title="Flights">
      {flights.map((f, i) => (
        <div key={i} className="flex items-center justify-between gap-2">
          <span>
            <LinkOut href={f.booking_link}>{f.airline}</LinkOut>
            {f.stops != null ? ` · ${f.stops === 0 ? "nonstop" : `${f.stops} stop(s)`}` : ""}
          </span>
          <span className="flex items-center gap-2">
            <span className="tabular-nums">{renderPrice(f.price, homeCurrency, rate)}</span>
            <SourceChip tool={f.source_tool} />
          </span>
        </div>
      ))}
    </Section>
  )
}
