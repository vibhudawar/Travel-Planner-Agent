import type { Metadata } from "next"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"

import "./globals.css"

export const metadata: Metadata = {
  title: "Trip Planner",
  description: "Plan trips with sourced, verified itineraries.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider>{children}</ThemeProvider>
        <Toaster />
      </body>
    </html>
  )
}
