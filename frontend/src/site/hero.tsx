import type { ReactNode } from "react";

/** The dark band every site page opens with (0.11.07 look): an optional breadcrumb, the eyebrow, the page's only H1,
 * one line of copy, and anything the page adds below it. */
export function PageHero({
  eyebrow,
  title,
  copy,
  id,
  crumbs,
  children,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  /** The H1's id, for a section labelled by it. */
  id?: string;
  /** A breadcrumb shown above the eyebrow. */
  crumbs?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="ms-page-hero ms-dark">
      {crumbs}
      <span className="ms-eyebrow">{eyebrow}</span>
      <h1 id={id}>{title}</h1>
      <p>{copy}</p>
      {children}
    </section>
  );
}
