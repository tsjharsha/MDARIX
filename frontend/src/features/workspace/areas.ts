import type { WorkspaceSection } from "./workspaceContext";

/**
 * The five work areas of the one navigation (Persona Blueprint wave D, UX2): Today · Cases · Investigations ·
 * Products · Decisions & Reports. Each area is a rail destination (a persona's tab, access_control/personas.py) and
 * holds one or more screens; an area with more than one screen the person may open shows them in its own small menu
 * (AreaNav). Records & trust, Team, Settings and Administration are not areas: they sit in the avatar menu.
 */
export const AREAS: Readonly<Record<string, { label: string; sections: readonly WorkspaceSection[] }>> = {
  // Look ahead and Next steps (a trial's) fold into Today.
  home: { label: "Today", sections: ["My Work", "Look ahead", "Next steps"] },
  complaints: { label: "Cases", sections: ["Complaints", "Complaint"] },
  investigations: { label: "Investigations", sections: ["Investigations"] },
  products: { label: "Products", sections: ["Product 360", "Trends"] },
  decisions: { label: "Decisions & Reports", sections: ["Approvals", "Decision trees", "Reports"] },
};

/** Each screen's name in its area's menu, where it differs from the screen's own. */
export const AREA_LINK_LABELS: Partial<Record<WorkspaceSection, string>> = {
  "My Work": "Today",
  "Product 360": "Products and suppliers",
  Reports: "Authority reports",
};

/** The area a screen belongs to, or null (Getting started, Records, Settings, Account, Administration...). */
export const areaOf = (section: string): string | null =>
  Object.entries(AREAS).find(([, area]) => (area.sections as readonly string[]).includes(section))?.[0] ?? null;

/** The screens of an area this person may open, in the area's order (one complaint's page is never listed). */
export const areaSections = (area: string, visible: readonly string[]): WorkspaceSection[] =>
  (AREAS[area]?.sections ?? []).filter((section) => section !== "Complaint" && visible.includes(section));

/** Where a rail destination opens: the screen itself when the person may open it, else the first screen of its area
 * they may (Decisions & Reports opens Approvals for a signer, Decision trees for anyone else). */
export const areaEntry = (section: WorkspaceSection, visible: readonly string[]): WorkspaceSection => {
  if (visible.includes(section)) return section;
  const area = areaOf(section);
  return (area && areaSections(area, visible)[0]) || section;
};
