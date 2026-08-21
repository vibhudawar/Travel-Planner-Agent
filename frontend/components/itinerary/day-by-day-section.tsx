import type { DayPlan } from "@/types/itinerary"

import { Section } from "./shared"

export function DayByDaySection({ days }: { days: DayPlan[] }) {
  if (days.length === 0) return null

  return (
    <Section title="Day by day">
      <ol className="flex flex-col gap-3">
        {days.map((d) => (
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
  )
}
