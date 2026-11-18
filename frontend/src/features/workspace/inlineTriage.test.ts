import { describe, expect, it } from "vitest";
import { triageItemOf } from "./sections/Triage";
import type { TriageList } from "./intake";

const item = (kind: string, id: string, linked: { kind: string; id: string; ref: string }[] = []) =>
  ({ key: `${kind}:${id}`, kind, id, ref: id, linked }) as unknown as TriageList["items"][number];

// The complaint page draws the triage form from its event's item (Triage.tsx InlineTriage). Once a Case is attached
// to the complaint (SAMPLE-CASE-11 onto SAMPLE-RV-11), the Case leads the event and the complaint is a linked record:
// the form must still be found, or the page says "the triage record is first in Details" and shows none.
describe("the complaint page's triage item", () => {
  it("is the complaint's own item", () => {
    expect(triageItemOf([item("COMPLAINT", "c-1")], "c-1")?.key).toBe("COMPLAINT:c-1");
  });

  it("is the Case's item when the complaint is linked into it", () => {
    const items = [
      item("COMPLAINT", "c-2"),
      item("INTAKE", "case-11", [{ kind: "COMPLAINT", id: "rv-11", ref: "SAMPLE-RV-11" }]),
    ];
    expect(triageItemOf(items, "rv-11")?.key).toBe("INTAKE:case-11");
  });

  it("is none for a complaint the list does not hold", () => {
    expect(triageItemOf([item("INTAKE", "case-11", [{ kind: "INTAKE", id: "x", ref: "X" }])], "rv-11")).toBeUndefined();
  });
});
