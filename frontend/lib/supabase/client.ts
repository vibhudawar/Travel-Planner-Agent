import { createBrowserClient } from "@supabase/ssr"

// Browser Supabase client (auth only). Uses the public publishable key — safe in the client.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  )
}
