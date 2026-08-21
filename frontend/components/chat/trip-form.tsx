"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { LocationAutocomplete, type Place } from "./location-autocomplete"

// Structured trip setup shown in the empty state — like a flight search form. The
// user picks real airports (codes resolved up front), and this composes a precise
// prompt for the agent so it never has to guess airport codes or ask for basics.
export function TripForm({ onPlan }: { onPlan: (message: string) => void }) {
  const [from, setFrom] = useState<Place | null>(null)
  const [to, setTo] = useState<Place | null>(null)
  const [depart, setDepart] = useState("")
  const [ret, setRet] = useState("")
  const [travelers, setTravelers] = useState(2)
  const [budget, setBudget] = useState("")

  const ready = Boolean(from && to && depart)

  function submit() {
    if (!from || !to || !depart) return
    const parts = [
      `Plan a trip from ${from.city} (${from.iata}) to ${to.city} (${to.iata})`,
      `departing ${depart}${ret ? `, returning ${ret}` : ""}`,
      `for ${travelers} traveler${travelers > 1 ? "s" : ""}`,
    ]
    if (budget.trim()) parts.push(`with a budget of ₹${Number(budget).toLocaleString("en-IN")}`)
    onPlan(parts.join(", ") + ".")
  }

  return (
    <div className="mt-6 grid gap-3 rounded-xl border bg-card p-4 text-left">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="From">
          <LocationAutocomplete value={from} onChange={setFrom} placeholder="City or airport" />
        </Field>
        <Field label="To">
          <LocationAutocomplete value={to} onChange={setTo} placeholder="City or airport" />
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Depart">
          <Input type="date" value={depart} onChange={(e) => setDepart(e.target.value)} />
        </Field>
        <Field label="Return">
          <Input type="date" value={ret} onChange={(e) => setRet(e.target.value)} />
        </Field>
        <Field label="Travelers">
          <Input
            type="number"
            min={1}
            value={travelers}
            onChange={(e) => setTravelers(Math.max(1, Number(e.target.value) || 1))}
          />
        </Field>
        <Field label="Budget (₹)">
          <Input
            type="number"
            min={0}
            value={budget}
            placeholder="optional"
            onChange={(e) => setBudget(e.target.value)}
          />
        </Field>
      </div>
      <Button onClick={submit} disabled={!ready} className="sm:justify-self-end">
        Plan my trip
      </Button>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-muted-foreground">
      {label}
      {children}
    </label>
  )
}
