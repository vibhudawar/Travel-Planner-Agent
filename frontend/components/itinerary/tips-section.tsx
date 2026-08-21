import { Section } from "./shared"

export function TipsSection({ tips }: { tips: string[] }) {
  if (tips.length === 0) return null

  return (
    <Section title="Tips">
      <ul className="list-disc pl-5 text-muted-foreground">
        {tips.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </Section>
  )
}
