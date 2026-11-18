import "./areaNav.css";
import { AREAS, AREA_LINK_LABELS, areaOf, areaSections } from "./areas";
import { sectionIcon } from "./HybridShell";
import type { WorkspaceSection } from "./workspaceContext";

/**
 * A work area's own small menu (UX2): the screens of the area this person may open, as links in a labelled
 * navigation landmark (not a tab list), the current one marked. Shown only when the area has more than one of them:
 * Today (with a trial's Look ahead and Next steps), Products (Products and suppliers, Trends) and Decisions & Reports
 * (Approvals, Decision trees, Authority reports).
 */
export function AreaNav({
  section,
  visible,
  open,
}: {
  section: WorkspaceSection;
  visible: readonly string[];
  open: (section: WorkspaceSection) => void;
}) {
  const area = areaOf(section);
  const links = area ? areaSections(area, visible) : [];
  if (!area || links.length < 2) return null;
  return (
    <nav className="uw-areanav" aria-label={`${AREAS[area].label} pages`}>
      {links.map((name) => {
        const Icon = sectionIcon(name);
        return (
          <button
            key={name}
            type="button"
            aria-current={name === section ? "page" : undefined}
            onClick={() => open(name)}
          >
            <Icon size={16} aria-hidden="true" />
            <span>{AREA_LINK_LABELS[name] ?? name}</span>
          </button>
        );
      })}
    </nav>
  );
}
