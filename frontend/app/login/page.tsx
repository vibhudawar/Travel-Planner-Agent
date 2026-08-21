"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createClient } from "@/lib/supabase/client"

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<"signin" | "signup">("signin")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!email || !password) return
    setBusy(true)
    const supabase = createClient()
    try {
      if (mode === "signup") {
        const { error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        toast.success("Account created. Check your email if confirmation is required.")
        router.replace("/")
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        router.replace("/")
      }
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Authentication failed")
    } finally {
      setBusy(false)
    }
  }

  const signup = mode === "signup"

  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
      <div className="w-full max-w-sm md:max-w-3xl">
        <div className="overflow-hidden rounded-2xl bg-card text-card-foreground shadow-sm ring-1 ring-foreground/10">
          <div className="grid md:min-h-[480px] md:grid-cols-2">
            {/* Brand panel — hidden on mobile. */}
            <div className="relative hidden bg-gradient-to-br from-primary via-primary to-primary/80 md:block">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 opacity-[0.12]"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 20% 20%, white 1px, transparent 1px), radial-gradient(circle at 80% 65%, white 1px, transparent 1px)",
                  backgroundSize: "38px 38px",
                }}
              />
              <div className="relative flex h-full flex-col p-8 text-white">
                <span className="w-fit text-2xl font-semibold tracking-tight">Trip Planner</span>
                <div className="mt-auto space-y-3">
                  <p className="text-2xl font-semibold leading-[1.2] tracking-tight text-balance">
                    Plan trips you can actually trust.
                  </p>
                  <p className="text-sm leading-relaxed text-white/80">
                    Sourced flights, hotels, and weather — every fact shows where it came from.
                  </p>
                </div>
              </div>
            </div>

            {/* Form panel */}
            <div className="flex items-center p-6 md:p-8">
              <div className="w-full">
                <span className="mb-6 inline-block text-2xl font-semibold tracking-tight md:hidden">
                  Trip Planner
                </span>

                <div className="flex flex-col gap-1.5">
                  <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                    {signup ? "Create your account" : "Welcome back"}
                  </h1>
                  <p className="text-sm text-balance text-muted-foreground">
                    {signup
                      ? "Start planning sourced, verified trips."
                      : "Log in to your Trip Planner account."}
                  </p>
                </div>

                <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="email" className="text-sm font-medium">
                      Email
                    </label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      autoComplete="email"
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="password" className="text-sm font-medium">
                      Password
                    </label>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      autoComplete={signup ? "new-password" : "current-password"}
                      required
                      minLength={6}
                    />
                  </div>
                  <Button type="submit" disabled={busy} className="w-full">
                    {busy ? "Please wait…" : signup ? "Sign up" : "Log in"}
                  </Button>
                </form>

                <p className="mt-6 text-center text-sm text-muted-foreground">
                  {signup ? "Have an account?" : "No account?"}{" "}
                  <button
                    type="button"
                    onClick={() => setMode(signup ? "signin" : "signup")}
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    {signup ? "Log in" : "Sign up"}
                  </button>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
