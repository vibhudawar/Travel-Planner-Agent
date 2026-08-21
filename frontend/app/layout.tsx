import type { Metadata } from "next"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/sonner"

import "./globals.css"
import { Outfit, Raleway } from "next/font/google";
import { cn } from "@/lib/utils";

const ralewayHeading = Raleway({subsets:['latin'],variable:'--font-heading'});

const outfit = Outfit({subsets:['latin'],variable:'--font-sans'});

export const metadata: Metadata = {
  title: "Trip Planner",
  description: "Plan trips with sourced, verified itineraries.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("font-sans", outfit.variable, ralewayHeading.variable)}>
      <body className="antialiased" suppressHydrationWarning>
        <ThemeProvider>{children}</ThemeProvider>
        <Toaster />
      </body>
    </html>
  )
}
