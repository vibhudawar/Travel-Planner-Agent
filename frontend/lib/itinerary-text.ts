import type { Itinerary } from "@/types/itinerary"

const SYMBOL: Record<string, string> = { USD: "$", INR: "₹", EUR: "€", GBP: "£", JPY: "¥" }

function fmt(usd: number | null | undefined, home: string | null | undefined, rate: number | null | undefined) {
  if (usd == null) return "—"
  const usdStr = `$${Math.round(usd).toLocaleString("en-IN")}`
  if (home && rate) {
    return `${SYMBOL[home] ?? home + " "}${Math.round(usd * rate).toLocaleString("en-IN")} (${usdStr})`
  }
  return usdStr
}

// Plain-text rendering of an itinerary for "copy as text" (chat + public page).
export function itineraryToText(it: Itinerary): string {
  const { budget } = it
  const home = budget.home_currency
  const rate = budget.fx_rate
  const lines: string[] = []

  lines.push(`Trip to ${it.destination}`)
  const meta = [it.start_date, it.end_date].filter(Boolean).join(" → ")
  if (meta) lines.push(`${meta}${it.travelers ? ` · ${it.travelers} traveler(s)` : ""}`)

  if (budget.total != null) {
    lines.push("", "BUDGET")
    for (const item of budget.items) lines.push(`  ${item.label}: ${fmt(item.amount, home, rate)}`)
    lines.push(`  Total: ${fmt(budget.total, home, rate)}`)
    if (budget.assessment) lines.push(`  ${budget.assessment}`)
  }

  if (it.flights.length) {
    lines.push("", "FLIGHTS")
    for (const f of it.flights) {
      const stops = f.stops == null ? "" : f.stops === 0 ? " · nonstop" : ` · ${f.stops} stop(s)`
      lines.push(`  ${f.airline}${stops} — ${fmt(f.price, home, rate)}${f.booking_link ? `  ${f.booking_link}` : ""}`)
    }
  }

  if (it.hotels.length) {
    lines.push("", "HOTELS")
    for (const h of it.hotels) {
      const rating = h.rating ? ` · ${h.rating}★` : ""
      const per = h.price_per_night != null ? "/night" : ""
      lines.push(`  ${h.name}${rating} — ${fmt(h.price_per_night, home, rate)}${per}${h.link ? `  ${h.link}` : ""}`)
    }
  }

  if (it.weather.length) {
    lines.push("", "WEATHER")
    for (const w of it.weather) lines.push(`  ${w.summary}`)
    const note = it.weather.find((w) => w.label)?.label
    if (note) lines.push(`  (${note})`)
  }

  if (it.attractions.length) {
    lines.push("", "ATTRACTIONS")
    for (const a of it.attractions) lines.push(`  - ${a.name}${a.link ? `  ${a.link}` : ""}`)
  }

  if (it.days.length) {
    lines.push("", "DAY BY DAY")
    for (const d of it.days) {
      lines.push(`  Day ${d.day}${d.title ? ` — ${d.title}` : ""}`)
      for (const act of d.activities) lines.push(`    • ${act}`)
    }
  }

  if (it.tips.length) {
    lines.push("", "TIPS")
    for (const t of it.tips) lines.push(`  - ${t}`)
  }

  lines.push("", "Prices are as-of retrieval — reverify before booking. Planned with Trip Planner.")
  return lines.join("\n")
}
