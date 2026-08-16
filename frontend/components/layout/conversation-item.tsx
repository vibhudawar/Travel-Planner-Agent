"use client"

import Link from "next/link"

import { SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import type { ConversationSummary } from "@/lib/api"

export function ConversationItem({
  conversation,
  active,
}: {
  conversation: ConversationSummary
  active: boolean
}) {
  return (
    <SidebarMenuItem>
      <SidebarMenuButton isActive={active} render={<Link href={`/?c=${conversation.id}`} />}>
        <span className="truncate">{conversation.title || "New chat"}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}
