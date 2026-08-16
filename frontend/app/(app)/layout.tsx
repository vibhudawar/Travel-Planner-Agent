import { redirect } from "next/navigation"

import { AppSidebar } from "@/components/layout/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { listConversations, type ConversationSummary } from "@/lib/api"
import { createClient } from "@/lib/supabase/server"

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect("/login")

  let conversations: ConversationSummary[] = []
  try {
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (token) conversations = await listConversations(token)
  } catch {
    // Backend unreachable — render the shell with an empty history rather than failing.
  }

  return (
    <SidebarProvider>
      <AppSidebar user={{ email: user.email ?? "" }} conversations={conversations} />
      <SidebarInset className="min-h-0">
        <header className="flex h-12 shrink-0 items-center px-2">
          <SidebarTrigger />
        </header>
        <div className="min-h-0 flex-1">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  )
}
