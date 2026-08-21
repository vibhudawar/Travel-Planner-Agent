import type { Budget } from "@/types/itinerary"

import { money, renderPrice, Section } from "./shared"

export function BudgetSection({ budget }: { budget: Budget }) {
  if (budget.total == null) return null
  const homeCcy = budget.home_currency
  const rate = budget.fx_rate

  return (
    <Section title="Budget">
      <div className="flex flex-col gap-1">
        {budget.items.map((it, i) => (
          <div key={i} className="flex justify-between gap-2">
            <span className="text-muted-foreground">{it.label}</span>
            <span className="tabular-nums">{renderPrice(it.amount, homeCcy, rate)}</span>
          </div>
        ))}
        <div className="flex justify-between gap-2 border-t pt-1 font-semibold">
          <span>Total</span>
          <span className="tabular-nums">{renderPrice(budget.total, homeCcy, rate)}</span>
        </div>
      </div>

      {budget.assessment && (
        <div
          className={`mt-1 rounded-lg border p-2 text-xs ${
            budget.over_budget
              ? "border-destructive/40 bg-destructive/10 text-destructive"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          }`}
        >
          {budget.assessment}
        </div>
      )}
      {budget.fx_note && homeCcy && (
        <p className="text-[0.65rem] text-muted-foreground">
          {budget.fx_note} (~{money(rate, homeCcy)}/$)
        </p>
      )}
    </Section>
  )
}
