import { AlertTriangle } from "lucide-react"

import type { Itinerary } from "@/types/itinerary"

import { AsOf } from "./as-of"
import { AttractionsSection } from "./attractions-section"
import { BudgetSection } from "./budget-section"
import { DayByDaySection } from "./day-by-day-section"
import { FlightsSection } from "./flights-section"
import { HotelsSection } from "./hotels-section"
import { TipsSection } from "./tips-section"
import { WeatherSection } from "./weather-section"

export function ItineraryView({ itinerary }: { itinerary: Itinerary }) {
  const { budget, verification } = itinerary
  const asOf = itinerary.provenance[0]?.retrieved_at
  const homeCcy = budget.home_currency
  const rate = budget.fx_rate

  return (
    <div className="mt-3 flex flex-col gap-5 rounded-xl border bg-card p-4 text-sm">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{itinerary.destination}</h2>
          <p className="text-xs text-muted-foreground">
            {[itinerary.start_date, itinerary.end_date].filter(Boolean).join(" → ")}
            {itinerary.travelers ? ` · ${itinerary.travelers} traveler(s)` : ""}
          </p>
        </div>
        {asOf && <AsOf iso={asOf} />}
      </header>

      {verification && verification.disclaimers.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
          <ul className="list-disc pl-4">
            {verification.disclaimers.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </div>
      )}

      <BudgetSection budget={budget} />
      <FlightsSection flights={itinerary.flights} homeCurrency={homeCcy} rate={rate} />
      <HotelsSection hotels={itinerary.hotels} homeCurrency={homeCcy} rate={rate} />
      <WeatherSection weather={itinerary.weather} />
      <AttractionsSection attractions={itinerary.attractions} />
      <DayByDaySection days={itinerary.days} />
      <TipsSection tips={itinerary.tips} />
    </div>
  )
}
