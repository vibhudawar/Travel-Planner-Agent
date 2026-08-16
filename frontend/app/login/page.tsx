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

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold tracking-tight">Trip Planner</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {mode === "signin" ? "Sign in to plan your trips." : "Create an account to get started."}
        </p>
        <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
            aria-label="Email"
          />
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            minLength={6}
            aria-label="Password"
          />
          <Button type="submit" disabled={busy}>
            {mode === "signin" ? "Sign in" : "Sign up"}
          </Button>
        </form>
        <button
          type="button"
          onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          className="mt-4 text-sm text-muted-foreground hover:text-foreground"
        >
          {mode === "signin" ? "No account? Sign up" : "Have an account? Sign in"}
        </button>
      </div>
    </main>
  )
}
