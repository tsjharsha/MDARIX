import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  investigationRequestFor,
  useOpenInvestigation,
  WorkspaceContext,
  type OpenInvestigationRequest,
  type WorkspaceApi,
} from "./workspaceContext";

const complaintRow = {
  id: "0b6f8f9e-1111-4222-8333-444455556666",
  business_id: "CMP000012",
  complaint_identifier: "ACD-CMP-012",
  product_id: "9d1c2b3a-1111-4222-8333-444455556666",
  version: "B",
  description: "Occlusion alarm during infusion",
};

describe("investigationRequestFor", () => {
  it("builds the request from a complaint list row", () => {
    expect(investigationRequestFor(complaintRow)).toEqual({
      productId: complaintRow.product_id,
      version: "B",
      complaint: {
        id: complaintRow.id,
        business_id: "CMP000012",
        complaint_identifier: "ACD-CMP-012",
        description: "Occlusion alarm during infusion",
      },
    });
  });

  it("reads a signal's version identifier and source number", () => {
    const signal = {
      id: complaintRow.id,
      business_id: "CMP000012",
      signal_id: "ACD-CMP-012",
      product_id: complaintRow.product_id,
      version_identifier: "C",
      description: null,
    };
    expect(investigationRequestFor(signal)).toMatchObject({
      version: "C",
      complaint: { complaint_identifier: "ACD-CMP-012", description: null },
    });
  });

  it("is null without a complaint id or a product", () => {
    expect(investigationRequestFor({ ...complaintRow, product_id: null })).toBeNull();
    expect(investigationRequestFor({ ...complaintRow, id: "" })).toBeNull();
    expect(investigationRequestFor(null)).toBeNull();
  });
});

describe("useOpenInvestigation", () => {
  let captured: ReturnType<typeof useOpenInvestigation> = null;
  function Probe() {
    captured = useOpenInvestigation();
    return <span>{captured ? "available" : "hidden"}</span>;
  }

  const workspace = (session: WorkspaceApi["session"]) => {
    const requestOpenInvestigation = vi.fn();
    const open = vi.fn();
    const api = { session, open, work: { requestOpenInvestigation } } as unknown as WorkspaceApi;
    const markup = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api}>
        <Probe />
      </WorkspaceContext.Provider>,
    );
    return { markup, requestOpenInvestigation, open };
  };

  it("switches the context and opens Investigations for a role that may change records", () => {
    const { markup, requestOpenInvestigation, open } = workspace({
      allowed_menu: ["products", "investigations"],
      business_permissions: ["records.write"],
    });
    expect(markup).toContain("available");
    const request = investigationRequestFor(complaintRow) as OpenInvestigationRequest;
    captured?.(request);
    expect(requestOpenInvestigation).toHaveBeenCalledWith(request);
    expect(open).toHaveBeenCalledWith("Investigations", "All investigations");
  });

  it("is hidden for a read-only role or without the Investigations section", () => {
    expect(workspace({ allowed_menu: ["products", "investigations"], business_permissions: [] }).markup).toContain(
      "hidden",
    );
    expect(workspace({ allowed_menu: ["products"], business_permissions: ["records.write"] }).markup).toContain(
      "hidden",
    );
  });

  it("is hidden outside the workspace", () => {
    expect(renderToStaticMarkup(<Probe />)).toContain("hidden");
  });
});
