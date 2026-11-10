import type { RefObject } from "react";
import { Tabs } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { HUB_TABS, hubPlace, hubTab, type HubTab } from "../productHub";

/**
 * Work › Products on the new navigation (0.10.94, W1): Product 360 and Supplier 360, read-only. The tab carries the
 * product (and version) or the supplier, so every page has its own address.
 */
export function ProductHubSection({ tab, heading }: { tab?: string; heading?: RefObject<HTMLHeadingElement | null> }) {
  const { shownTab, reportTab } = useWorkspace();
  const place = hubPlace(shownTab ?? tab);
  const choose = (next: HubTab) => reportTab?.(hubTab({ tab: next }));
  void heading;
  return (
    <Tabs tabs={HUB_TABS} active={place.tab} onChange={choose} label="Products and suppliers">
      {null}
    </Tabs>
  );
}
