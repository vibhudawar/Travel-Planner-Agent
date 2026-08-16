import { createServerClient } from "@supabase/ssr"
import { cookies } from "next/headers"

// Server Supabase client (auth only). `cookies()` is async in Next 16.
export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            )
          } catch {
            // Called from a Server Component (read-only cookies) — safe to ignore;
            // the middleware refreshes the session cookie.
          }
        },
      },
    },
  )
}
