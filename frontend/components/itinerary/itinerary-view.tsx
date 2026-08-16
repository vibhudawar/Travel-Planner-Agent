import { AlertTriangle } from "lucide-react"

import type { Itinerary, SourceTool } from "@/types/itinerary"

const TOOL_LABEL: Record<SourceTool, string> = {
  search_flights: "flights",
  search_hotels: "hotels",
  search_weather: "weather",
  search_attractions: "attractions",
  search_youtube_vlogs: "youtube",
  google_search: "web",
}

function SourceChip({ tool }: { tool: SourceTool | null }) {
  if (!tool) return null
  return (
    <span className="rounded-full border px-1.5 py-0.5 text-[0.65rem] text-muted-foreground">
      via {TOOL_LABEL[tool]}
    </span>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

function money(amount: number | null, currency: string) {
  if (amount == null) return "—"
  return `${currency === "USD" ? "$" : currency + " "}${amount.toLocaleString()}`
}

export function ItineraryView({ itinerary }: { itinerary: Itinerary }) {
  const { budget, verification } = itinerary
  const asOf = itinerary.provenance[0]?.retrieved_at

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
        {asOf && (
          <span className="text-[0.65rem] text-muted-foreground">
            as of {new Date(asOf).toLocaleString()}
          </span>
        )}
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

      {budget.total != null && (
        <Section title="Budget">
          <div className="flex flex-col gap-1">
            {budget.items.map((it, i) => (
              <div key={i} className="flex justify-between">
                <span className="text-muted-foreground">{it.label}</span>
                <span className="tabular-nums">{money(it.amount, budget.currency)}</span>
              </div>
            ))}
            <div className="flex justify-between border-t pt-1 font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{money(budget.total, budget.currency)}</span>
            </div>
          </div>
        </Section>
      )}

      {itinerary.flights.length > 0 && (
        <Section title="Flights">
          {itinerary.flights.map((f, i) => (
            <div key={i} className="flex items-center justify-between gap-2">
              <span>
                {f.airline}
                {f.stops != null ? ` · ${f.stops === 0 ? "nonstop" : `${f.stops} stop(s)`}` : ""}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">{money(f.price, f.currency)}</span>
                <SourceChip tool={f.source_tool} />
              </span>
            </div>
          ))}
        </Section>
      )}

      {itinerary.hotels.length > 0 && (
        <Section title="Hotels">
          {itinerary.hotels.map((h, i) => (
            <div key={i} className="flex items-center justify-between gap-2">
              <span>
                {h.name}
                {h.rating ? ` · ${h.rating}★` : ""}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">
                  {money(h.price_per_night, h.currency)}
                  {h.price_per_night != null ? "/night" : ""}
                </span>
                <SourceChip tool={h.source_tool} />
              </span>
            </div>
          ))}
        </Section>
      )}

      {itinerary.weather.length > 0 && (
        <Section title="Weather">
          {itinerary.weather.map((w, i) => (
            <div key={i} className="flex flex-col gap-0.5">
              <p>{w.summary}</p>
              {w.label && <p className="text-[0.65rem] text-muted-foreground">{w.label}</p>}
            </div>
          ))}
        </Section>
      )}

      {itinerary.attractions.length > 0 && (
        <Section title="Attractions">
          <div className="flex flex-wrap gap-1.5">
            {itinerary.attractions.map((a, i) => (
              <span key={i} className="rounded-md border px-2 py-1 text-xs">
                {a.name}
              </span>
            ))}
          </div>
        </Section>
      )}

      {itinerary.days.length > 0 && (
        <Section title="Day by day">
          <ol className="flex flex-col gap-3">
            {itinerary.days.map((d) => (
              <li key={d.day}>
                <p className="font-medium">
                  Day {d.day}
                  {d.title ? ` — ${d.title}` : ""}
                </p>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                  {d.activities.map((act, i) => (
                    <li key={i}>{act}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {itinerary.tips.length > 0 && (
        <Section title="Tips">
          <ul className="list-disc pl-5 text-muted-foreground">
            {itinerary.tips.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}
