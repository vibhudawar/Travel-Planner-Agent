"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

// Assistant output is model-generated → untrusted. react-markdown does NOT render raw HTML by
// default (no rehype-raw here), so embedded <script>/<img onerror> etc. are inert. Links are
// forced to open safely. Never swap this for dangerouslySetInnerHTML.
export function Markdown({ children }: { children: string }) {
  return (
    <div
      className={
        "text-sm leading-relaxed break-words " +
        "[&_p]:my-2 first:[&_p]:mt-0 last:[&_p]:mb-0 " +
        "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 " +
        "[&_h1]:mt-3 [&_h1]:mb-1 [&_h1]:text-lg [&_h1]:font-semibold " +
        "[&_h2]:mt-3 [&_h2]:mb-1 [&_h2]:text-base [&_h2]:font-semibold " +
        "[&_h3]:mt-2 [&_h3]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold " +
        "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.85em] " +
        "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 " +
        "[&_pre_code]:bg-transparent [&_pre_code]:p-0 " +
        "[&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-2 " +
        "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground " +
        "[&_table]:my-2 [&_table]:w-full [&_table]:text-xs [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_th]:text-left " +
        "[&_td]:border [&_td]:px-2 [&_td]:py-1"
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer nofollow" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
