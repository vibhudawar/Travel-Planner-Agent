"use client"

import { useEffect, useRef, useState } from "react"

import { Input } from "@/components/ui/input"

export type Place = {
  iata: string
  name: string
  city: string
  country: string
  label: string
}

// Airport typeahead backed by /api/locations. The user picks a real airport, which
// disambiguates multi-airport cities (London → LHR/LGW/…) and duplicate city names.
export function LocationAutocomplete({
  value,
  onChange,
  placeholder,
  id,
}: {
  value: Place | null
  onChange: (place: Place | null) => void
  placeholder?: string
  id?: string
}) {
  const [query, setQuery] = useState(value?.label ?? "")
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = query.trim()
    const controller = new AbortController()
    const t = setTimeout(async () => {
      if (!q || (value && q === value.label)) {
        setResults([])
        return
      }
      try {
        const res = await fetch(`/api/locations?q=${encodeURIComponent(q)}&limit=6`, {
          signal: controller.signal,
        })
        if (!res.ok) return
        const data = (await res.json()) as { results: Place[] }
        setResults(data.results ?? [])
        setActive(0)
        setOpen(true)
      } catch {
        // aborted or offline — ignore
      }
    }, 200)
    return () => {
      clearTimeout(t)
      controller.abort()
    }
  }, [query, value])

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [])

  function pick(place: Place) {
    onChange(place)
    setQuery(place.label)
    setResults([])
    setOpen(false)
  }

  return (
    <div ref={boxRef} className="relative">
      <Input
        id={id}
        value={query}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value)
          onChange(null)
        }}
        onFocus={() => results.length > 0 && setOpen(true)}
        onKeyDown={(e) => {
          if (!open || results.length === 0) return
          if (e.key === "ArrowDown") {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, results.length - 1))
          } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === "Enter" && results[active]) {
            e.preventDefault()
            pick(results[active])
          } else if (e.key === "Escape") {
            setOpen(false)
          }
        }}
      />
      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg border bg-popover p-1 shadow-md">
          {results.map((r, i) => (
            <li key={r.iata}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(r)}
                className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                  i === active ? "bg-accent text-accent-foreground" : ""
                }`}
              >
                <span className="truncate">
                  {r.city} · <span className="text-muted-foreground">{r.name}</span>
                </span>
                <span className="shrink-0 rounded border px-1 text-[0.7rem] text-muted-foreground">
                  {r.iata}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
