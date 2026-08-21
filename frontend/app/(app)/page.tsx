import { ChatView } from "@/components/chat/chat-view"
import { getConversation, type ChatMessage } from "@/lib/api"
import { createClient } from "@/lib/supabase/server"

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<{ c?: string }>
}) {
  const { c: conversationId } = await searchParams

  let initialMessages: ChatMessage[] = []
  if (conversationId) {
    const supabase = await createClient()
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    if (token) {
      try {
        initialMessages = (await getConversation(conversationId, token)) ?? []
      } catch {
        // Backend momentarily unreachable — render the chat shell rather than
        // crashing the whole route; history reloads on the next navigation.
        initialMessages = []
      }
    }
  }

  // Key by conversation so switching threads mounts a fresh view with its history.
  return (
    <ChatView key={conversationId ?? "new"} conversationId={conversationId} initialMessages={initialMessages} />
  )
}
