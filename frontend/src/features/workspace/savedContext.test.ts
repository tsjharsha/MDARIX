import { describe, expect, it } from "vitest";
import {
  caseFromSearch,
  caseLinkStart,
  contextBody,
  modeFromServer,
  restoredChoice,
  searchWithoutCase,
  versionIdentifierFor,
} from "./savedContext";

const PRODUCT = "9d1c2b3a-1111-4222-8333-444455556666";
const VERSION = "1a2b3c4d-1111-4222-8333-444455556666";
const CASE = "0b6f8f9e-1111-4222-8333-444455556666";
const products = [{ id: PRODUCT }, { id: "other" }];

describe("saving the working context", () => {
  it("sends the product, version, case and time view, with a date only for a historical view", () => {
    expect(
      contextBody({
        productId: PRODUCT,
        versionId: VERSION,
        investigationId: CASE,
        mode: "current",
        asOf: "2026-10-06",
      }),
    ).toEqual({
      product_id: PRODUCT,
      product_version_id: VERSION,
      investigation_id: CASE,
      temporal_mode: "CURRENT",
      temporal_cutoff: null,
    });
    expect(
      contextBody({ productId: PRODUCT, versionId: null, investigationId: "", mode: "known", asOf: "2026-03-04" }),
    ).toEqual({
      product_id: PRODUCT,
      product_version_id: null,
      investigation_id: null,
      temporal_mode: "KNOWN_AS_OF",
      temporal_cutoff: "2026-03-04T00:00:00Z",
    });
  });

  it("reads the server's time modes", () => {
    expect(modeFromServer("CURRENT")).toBe("current");
    expect(modeFromServer("event_as_of")).toBe("event");
    expect(modeFromServer("KNOWN_AS_OF")).toBe("known");
    expect(modeFromServer("SOMETHING")).toBeNull();
    expect(modeFromServer(null)).toBeNull();
  });
});

describe("restoring the saved context", () => {
  it("starts from the saved product, version and case when the product still exists", () => {
    expect(
      restoredChoice(
        { product_id: PRODUCT, product_version_id: VERSION, investigation_id: CASE, temporal_mode: "CURRENT" },
        products,
      ),
    ).toEqual({ productId: PRODUCT, versionId: VERSION, investigationId: CASE, mode: null, asOf: null });
  });

  it("brings back a historical view with its date, never an old date for the current view", () => {
    expect(
      restoredChoice(
        { product_id: PRODUCT, temporal_mode: "EVENT_AS_OF", temporal_cutoff: "2026-03-04T00:00:00Z" },
        products,
      ),
    ).toMatchObject({ mode: "event", asOf: "2026-03-04" });
    expect(
      restoredChoice(
        { product_id: PRODUCT, temporal_mode: "CURRENT", temporal_cutoff: "2026-03-04T00:00:00Z" },
        products,
      ),
    ).toMatchObject({ mode: null, asOf: null });
    expect(restoredChoice({ product_id: PRODUCT, temporal_mode: "EVENT_AS_OF" }, products)).toMatchObject({
      mode: null,
      asOf: null,
    });
  });

  it("ignores a saved context whose product is gone, or an empty one", () => {
    expect(restoredChoice({ product_id: "removed", investigation_id: CASE }, products)).toBeNull();
    expect(restoredChoice({}, products)).toBeNull();
    expect(restoredChoice(null, products)).toBeNull();
  });

  it("finds the saved version's identifier among the product's versions", () => {
    const versions = [
      { id: "v1", version_identifier: "A" },
      { id: VERSION, version_identifier: "B" },
    ];
    expect(versionIdentifierFor(versions, VERSION)).toBe("B");
    expect(versionIdentifierFor(versions, "gone")).toBeNull();
    expect(versionIdentifierFor(versions, null)).toBeNull();
    expect(versionIdentifierFor(undefined, VERSION)).toBeNull();
  });
});

describe("case links", () => {
  it("reads the case's business ID from the address, and nothing else", () => {
    expect(caseFromSearch("?case=INV000147")).toBe("INV000147");
    expect(caseFromSearch("?tab=x&case=%20INV000147%20")).toBe("INV000147");
    expect(caseFromSearch("?case=")).toBeNull();
    expect(caseFromSearch("?case=<script>")).toBeNull();
    expect(caseFromSearch("")).toBeNull();
    expect(caseFromSearch(undefined)).toBeNull();
  });

  it("removes the case from the address and keeps the rest", () => {
    expect(searchWithoutCase("?case=INV000147")).toBe("");
    expect(searchWithoutCase("?case=INV000147&tab=x")).toBe("?tab=x");
    expect(searchWithoutCase("")).toBe("");
  });

  it("opens the case's workspace or its decision; other views as they are", () => {
    expect(caseLinkStart("investigations", ["Investigations"])).toEqual(["Investigations", "Workspace"]);
    expect(caseLinkStart("decision", ["Decisions"])).toEqual(["Decisions", "Decision center"]);
    expect(caseLinkStart("my-work", ["My Work"])).toEqual(["My Work"]);
    expect(caseLinkStart(undefined, ["Dashboard"])).toEqual(["Dashboard"]);
  });
});
