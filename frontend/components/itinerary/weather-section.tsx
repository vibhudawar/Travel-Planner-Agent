import type { WeatherDay } from "@/types/itinerary"

import { Section } from "./shared"

export function WeatherSection({ weather }: { weather: WeatherDay[] }) {
  if (weather.length === 0) return null
  // The forecast/seasonal caveat is identical across days — show it once.
  const note = weather.find((w) => w.label)?.label

  return (
    <Section title="Weather">
      <div className="flex flex-col gap-0.5">
        {weather.map((w, i) => (
          <p key={i}>{w.summary}</p>
        ))}
      </div>
      {note && <p className="mt-1 text-[0.65rem] text-muted-foreground">{note}</p>}
    </Section>
  )
}
