import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { DuplicateHits, LateEntryField, duplicatesPath, looksLate, recordAddress } from "./BackEntry";
import { routeFor } from "../../../app/linkTable";
import { HelpMenu, OUTAGE_SOP_PATH } from "../../shared/HelpMenu";

// B6a Part A (G18b-d): back-entry after an outage, and the SOP template in Help.
describe("back-entry after an outage", () => {
  const now = Date.parse("2026-11-11T12:00:00");

  it("asks the late-entry reason when a time on the form is old, never for a fresh call", () => {
    expect(looksLate(["2026-11-11T11:00", "", ""], now)).toBe(false);
    expect(looksLate(["2026-11-11T11:00", "2026-11-09T09:00", ""], now)).toBe(true);
    expect(looksLate(["", "not a time"], now)).toBe(false);
  });

  it("checks duplicates by product, lot, serial, site, country and the event day", () => {
    const path = duplicatesPath({
      product: "p-1",
      lot: "L 7",
      serial: "",
      site: "City Hospital",
      country: "IN",
      event: "2026-11-10T08:30",
    });
    expect(path).toBe(
      "/api/v1/intake/possible-duplicates?product_id=p-1&lot=L+7&serial=&site=City+Hospital&country=IN&event_on=2026-11-10",
    );
    // No product chosen: the lot alone, never an empty product id (the server would refuse it).
    expect(duplicatesPath({ product: "", lot: "L7", serial: "", site: "", country: "", event: "" })).toBe(
      "/api/v1/intake/possible-duplicates?lot=L7&serial=&site=&country=",
    );
  });

  it("explains that the clock counts from awareness and lists each possible duplicate with its reasons", () => {
    expect(renderToStaticMarkup(<LateEntryField value="" onChange={vi.fn()} />)).toContain(
      "The reporting clock still counts from when you became aware",
    );
    const hits = renderToStaticMarkup(
      <DuplicateHits
        hits={[{ kind: "COMPLAINT", id: "c1", ref: "SAMPLE-RV-11", source: "Sample complaint", reasons: ["same lot"] }]}
      />,
    );
    expect(hits).toContain("SAMPLE-RV-11");
    expect(hits).toContain("save anyway");
    // Navigation polish: the reference opens the record in a new tab, so the form stays.
    expect(hits).toContain('href="/app/readiness?tab=Oversight&amp;event=c1"');
    expect(hits).toContain('target="_blank"');
    expect(hits).toContain("(opens in a new tab)");
  });

  it("opens a complaint on its page (new navigation) or Oversight (classic), a Case on its check", () => {
    const complaint = { kind: "COMPLAINT", id: "c1", ref: "RV 06" };
    expect(recordAddress(complaint, "new")).toBe("/app/complaints/RV%2006");
    expect(recordAddress(complaint, "classic")).toBe("/app/readiness?tab=Oversight&event=c1");
    expect(recordAddress({ kind: "INTAKE", id: "i1", ref: "CASE-1" })).toBe(
      "/app/complaints?tab=First+contact&check=i1",
    );
    // The new navigation reads that former address as My work › Queues › Calls to check, the Case's check open.
    expect(routeFor("Complaints", "First contact?check=i1", "mvp", "new")).toEqual({
      section: "My Work",
      tab: "Queues?check=i1&view=Calls+to+check",
    });
  });

  it("offers the manual-workaround SOP template in Help, marked to confirm with a consultant", () => {
    const menu = renderToStaticMarkup(<HelpMenu onGettingStarted={vi.fn()} defaultOpen />);
    expect(OUTAGE_SOP_PATH).toBe("/help/outage-workaround-sop-template.txt");
    expect(menu).toContain(`href="${OUTAGE_SOP_PATH}"`);
    expect(menu).toContain("to confirm with your consultant");
  });
});
