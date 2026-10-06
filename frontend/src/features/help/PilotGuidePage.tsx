import { ArrowLeft, BookOpen } from "lucide-react";
// The guide's single source is PILOT_GUIDE.md beside this file (inside frontend/, so the web image build has it);
// it is bundled as text at build time.
import guide from "./PILOT_GUIDE.md?raw";
import { parseMarkdown, renderInline } from "../../site/markdown";

/** The guide as page blocks: its own "# title" becomes the page heading, "##" sections become h2 and "###" h3. */
export function guideBlocks(source: string) {
  const blocks = parseMarkdown(source);
  const title = blocks[0]?.kind === "heading" && blocks[0].level === 1 ? blocks.shift() : undefined;
  return { title: title && title.kind === "heading" ? title.text : "Pilot guide", blocks };
}

/**
 * The pilot guide at /help/pilot-guide, linked from the Help menu of every signed-in screen. It holds no
 * organization data, so it opens without a session (and can be read before the first sign-in).
 */
export function PilotGuidePage({ source = guide }: { source?: string }) {
  const { title, blocks } = guideBlocks(source);
  return (
    <div className="help-page">
      <a className="app-skip" href="#help-main">
        Skip to content
      </a>
      <header className="help-page-top">
        <a className="auth-brand" href="/app" aria-label="Back to MDARIX">
          <span className="auth-logo" aria-hidden="true">
            M
          </span>
          MDARIX
        </a>
        <a className="help-back" href="/app">
          <ArrowLeft size={15} aria-hidden="true" /> Back to MDARIX
        </a>
      </header>
      <main id="help-main" className="help-page-body" tabIndex={-1}>
        <p className="help-eyebrow">
          <BookOpen size={15} aria-hidden="true" /> Help
        </p>
        <h1>{title}</h1>
        {blocks.map((block, index) => {
          if (block.kind === "heading") {
            const Tag = (["h2", "h2", "h3"] as const)[block.level - 1];
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
      </main>
    </div>
  );
}
