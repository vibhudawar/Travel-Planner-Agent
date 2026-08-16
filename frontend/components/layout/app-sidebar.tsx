"use client"

import { Plus } from "lucide-react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import type { ConversationSummary } from "@/lib/api"

import { ConversationItem } from "./conversation-item"
import { ThemeToggle } from "./theme-toggle"
import { UserMenu } from "./user-menu"

export function AppSidebar({
  user,
  conversations,
}: {
  user: { email: string }
  conversations: ConversationSummary[]
}) {
  const activeConv = useSearchParams().get("c")

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1 py-1">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            ✈
          </div>
          <span className="text-base font-semibold group-data-[collapsible=icon]:hidden">
            Trip Planner
          </span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton tooltip="New chat" render={<Link href="/" />}>
                  <Plus className="size-4" />
                  <span>New chat</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>Recent</SidebarGroupLabel>
          <SidebarGroupContent>
            {conversations.length === 0 ? (
              <p className="px-2 py-1.5 text-xs text-muted-foreground">No conversations yet.</p>
            ) : (
              <SidebarMenu>
                {conversations.map((c) => (
                  <ConversationItem key={c.id} conversation={c} active={activeConv === c.id} />
                ))}
              </SidebarMenu>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="gap-1 border-t">
        <div className="flex items-center justify-between px-1 group-data-[collapsible=icon]:justify-center">
          <span className="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
            Appearance
          </span>
          <ThemeToggle />
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <UserMenu user={user} />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
