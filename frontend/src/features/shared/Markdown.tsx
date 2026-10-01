import type { ReactNode } from "react";

/**
 * Safe Markdown for AI answers: headings, paragraphs, lists, tables, bold, italics, inline code and [EVIDENCE-ID]
 * citations. Everything is built as React elements (never raw HTML), so model output cannot inject markup or
 * scripts. Links are shown as their text only; nothing in an AI answer is clickable.
 */

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "rule" };

const HEADING = /^(#{1,6})\s+(.*)$/;
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.replace(/\s*<br\s*\/?>\s*/gi, "; ").trim());

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2].replace(/#+\s*$/, "").trim() });
      continue;
    }
    if (line.trim().startsWith("|") && TABLE_SEPARATOR.test(lines[i + 1] ?? "")) {
      flush();
      const header = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      i -= 1;
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    if (RULE.test(line)) {
      flush();
      blocks.push({ kind: "rule" });
      continue;
    }
    const bullet = line.match(BULLET);
    const numbered = line.match(NUMBERED);
    if (bullet || numbered) {
      flush();
      const ordered = !bullet;
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (i < lines.length) {
        const item = lines[i].match(pattern);
        if (item) items.push(item[1]);
        else if (lines[i].trim() && /^\s{2,}\S/.test(lines[i]) && items.length)
          items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    paragraph.push(line.trim());
  }
  flush();
  return blocks;
}

const INLINE =
  /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)]*\)|\[[A-Za-z0-9][A-Za-z0-9_.:/-]*\])/g;

export function Inline({ text, citations }: { text: string; citations?: Set<string> }) {
  // Models often bold a citation inside its brackets: [**EV-1**] reads as the citation [EV-1].
  const parts = text
    .replace(/\[\*\*([^*\]]+)\*\*\]/g, "[$1]")
    .split(INLINE)
    .filter((part) => part !== "");
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
        if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__")))
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
          return <em key={index}>{part.slice(1, -1)}</em>;
        const link = part.match(/^\[([^\]]+)\]\([^)]*\)$/);
        if (link) return <span key={index}>{link[1]}</span>;
        const cite = part.match(/^\[([A-Za-z0-9][A-Za-z0-9_.:/-]*)\]$/);
        if (cite)
          return (
            <span
              key={index}
              className={`md-cite${citations?.has(cite[1]) ? " is-known" : ""}`}
              title={citations?.has(cite[1]) ? "Cited evidence" : undefined}
            >
              {cite[1]}
            </span>
          );
        return <span key={index}>{part}</span>;
      })}
    </>
  );
}

export function Markdown({ source, citations }: { source: string; citations?: Set<string> }) {
  const blocks = parseMarkdown(source);
  const nodes: ReactNode[] = blocks.map((block, index) => {
    switch (block.kind) {
      case "heading":
        return block.level <= 2 ? (
          <h3 key={index}>
            <Inline text={block.text} citations={citations} />
          </h3>
        ) : (
          <h4 key={index}>
            <Inline text={block.text} citations={citations} />
          </h4>
        );
      case "paragraph":
        return (
          <p key={index}>
            <Inline text={block.text} citations={citations} />
          </p>
        );
      case "list": {
        const items = block.items.map((item, itemIndex) => (
          <li key={itemIndex}>
            <Inline text={item} citations={citations} />
          </li>
        ));
        return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
      }
      case "table":
        return (
          <div className="md-table-wrap" key={index}>
            <table>
              <thead>
                <tr>
                  {block.header.map((cell, cellIndex) => (
                    <th key={cellIndex} scope="col">
                      <Inline text={cell} citations={citations} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>
                        <Inline text={cell} citations={citations} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      default:
        return <hr key={index} />;
    }
  });
  return <div className="md-body">{nodes}</div>;
}
