// Mirrors the backend Itinerary schema (schema.py). The frontend renders these
// as the trust surface: every fact shows its source and freshness.

export type SourceTool =
  | "search_flights"
  | "search_hotels"
  | "search_weather"
  | "search_attractions"
  | "search_youtube_vlogs"
  | "google_search"

export type FlightOption = {
  airline: string
  price: number | null
  currency: string
  depart_time: string | null
  arrive_time: string | null
  stops: number | null
  booking_link: string | null
  source_tool: SourceTool
}

export type HotelOption = {
  name: string
  price_per_night: number | null
  currency: string
  rating: number | null
  link: string | null
  source_tool: SourceTool
}

export type Activity = {
  name: string
  kind?: string | null
  notes?: string | null
  source_tool: SourceTool
}

export type WeatherDay = {
  date: string | null
  summary: string
  is_forecast: boolean | null
  label: string | null
  source_tool: SourceTool
}

export type DayPlan = {
  day: number
  date: string | null
  title: string | null
  activities: string[]
  notes: string | null
}

export type BudgetItem = { label: string; amount: number; source_tool: SourceTool | null }
export type Budget = { currency: string; items: BudgetItem[]; total: number | null }
export type Source = { tool: SourceTool; retrieved_at: string; summary: string | null }

export type Verification = {
  status: string
  n_removed: number
  disclaimers: string[]
  verifier_model: string
}

export type Itinerary = {
  destination: string
  origin: string | null
  start_date: string | null
  end_date: string | null
  travelers: number | null
  overview: string | null
  flights: FlightOption[]
  hotels: HotelOption[]
  weather: WeatherDay[]
  attractions: Activity[]
  days: DayPlan[]
  budget: Budget
  tips: string[]
  provenance: Source[]
  generated_at: string | null
  verification: Verification | null
}
