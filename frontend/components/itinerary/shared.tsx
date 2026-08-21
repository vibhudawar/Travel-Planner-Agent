import { ExternalLink } from "lucide-react"

import type { SourceTool } from "@/types/itinerary"

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$",
  INR: "₹",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
}

const TOOL_LABEL: Record<SourceTool, string> = {
  search_flights: "flights",
  search_hotels: "hotels",
  search_weather: "weather",
  search_attractions: "attractions",
  search_youtube_vlogs: "youtube",
  google_search: "web",
}

export function SourceChip({ tool }: { tool: SourceTool | null }) {
  if (!tool) return null
  return (
    <span className="rounded-full border px-1.5 py-0.5 text-[0.65rem] text-muted-foreground">
      via {TOOL_LABEL[tool]}
    </span>
  )
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

export function money(amount: number | null | undefined, currency: string) {
  if (amount == null) return "—"
  const sym = CURRENCY_SYMBOL[currency?.toUpperCase()] ?? `${currency} `
  // Fixed locale so server and client format identically (avoids hydration mismatch);
  // en-IN also gives the ₹ lakh grouping (₹1,64,776).
  return `${sym}${Math.round(amount).toLocaleString("en-IN")}`
}

// Render a USD amount in the user's home currency (primary) with USD in parens for
// reference. When no home currency is set, shows USD only. Home conversion uses the
// live, code-computed FX rate carried on the budget — never an LLM guess.
export function renderPrice(
  usd: number | null | undefined,
  homeCurrency: string | null | undefined,
  rate: number | null | undefined,
  suffix = "",
): React.ReactNode {
  if (usd == null) return "—"
  const usdStr = money(usd, "USD")
  if (homeCurrency && rate) {
    return (
      <>
        {money(usd * rate, homeCurrency)}
        {suffix}
        <span className="ml-1 text-xs font-normal text-muted-foreground">({usdStr})</span>
      </>
    )
  }
  return (
    <>
      {usdStr}
      {suffix}
    </>
  )
}

// A price/label that links out to booking/maps when a URL is available.
export function LinkOut({ href, children }: { href?: string | null; children: React.ReactNode }) {
  if (!href) return <>{children}</>
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
    >
      {children}
      <ExternalLink className="size-3 shrink-0" />
    </a>
  )
}
