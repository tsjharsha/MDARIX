import type { ReactNode } from "react";

/*
 * A deliberately small Markdown renderer for the lawyer-supplied legal documents (legal/README.md): headings,
 * paragraphs, bulleted and numbered lists, **bold** and links. It builds React elements, never HTML strings, so the
 * text cannot inject markup, and links are kept only for https, http, mailto and same-site paths.
 */

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] };

const HEADING = /^(#{1,3})\s+(.*)$/;
const BULLET = /^\s*[-*]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    if (list) blocks.push({ kind: "list", ...list });
    paragraph = [];
    list = null;
  };
  for (const raw of source.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const heading = HEADING.exec(line);
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    if (!line.trim()) flush();
    else if (heading) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2].trim() });
    } else if (bullet || numbered) {
      const ordered = Boolean(numbered && !bullet);
      const text = (bullet ?? numbered)![1].trim();
      if (paragraph.length || (list && list.ordered !== ordered)) flush();
      list ??= { ordered, items: [] };
      list.items.push(text);
    } else if (list && /^\s+/.test(raw)) {
      // An indented line continues the previous list item.
      list.items[list.items.length - 1] += ` ${line.trim()}`;
    } else {
      if (list) flush();
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}

export function safeHref(href: string): string | null {
  const value = href.trim();
  if (/^(https?:|mailto:)/i.test(value)) return value;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  return null;
}

const INLINE = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g;

export function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    if (match[1] !== undefined) nodes.push(<strong key={index}>{match[1]}</strong>);
    else {
      const href = safeHref(match[3]);
      nodes.push(
        href ? (
          <a key={index} href={href} rel={href.startsWith("http") ? "noopener noreferrer" : undefined}>
            {match[2]}
          </a>
        ) : (
          match[2]
        ),
      );
    }
    last = index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function Markdown({ source }: { source: string }) {
  const blocks = parseMarkdown(source);
  // The page shows the document's title as its own h1, so a leading "# Title" line is not repeated.
  if (blocks[0]?.kind === "heading" && blocks[0].level === 1) blocks.shift();
  return (
    <>
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          // The page already has its own h1, so document headings start one level lower.
          const Tag = (["h2", "h3", "h4"] as const)[block.level - 1];
          return <Tag key={index}>{renderInline(block.text)}</Tag>;
        }
        if (block.kind === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </Tag>
          );
        }
        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </>
  );
}
