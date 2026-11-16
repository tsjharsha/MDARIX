import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SignaturesView } from "./sections/AuditTab";

// Hero front end (WHIF): the signatures name the signer and the time, and "all valid" leads as a seal row.
const signature = {
  signature_id: "s-1",
  business_id: "SIG000001",
  valid: true,
  decision: "APPROVED",
  signer_name: "Priya Sharma",
  signer_role: "REGULATORY_LEADER",
  signed_at: "2026-11-10T09:30:00+00:00",
  meaning: "Approval",
};

describe("signature verification", () => {
  it("names each signer with the time, under a seal row when every signature is valid", () => {
    const html = renderToStaticMarkup(
      <SignaturesView
        verification={{ state: "ready", data: { verification_status: "VALID", signatures: [signature] } }}
      />,
    );
    expect(html).toContain('class="uw-seal"');
    expect(html).toContain("1 signature");
    expect(html).toContain("unchanged since signing");
    expect(html).toContain("<strong>Priya Sharma</strong>");
    expect(html).toMatch(/10 Nov 2026, \d{2}:\d{2}/);
    const broken = renderToStaticMarkup(
      <SignaturesView
        verification={{
          state: "ready",
          data: { verification_status: "INVALID", signatures: [{ ...signature, valid: false }] },
        }}
      />,
    );
    expect(broken).not.toContain('class="uw-seal"');
  });
});
