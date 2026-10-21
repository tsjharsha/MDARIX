import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CUSTOMER_APPROVAL_REQUIRED, CUSTOMER_APPROVAL_TEXT, Panel } from "./console/charts";

// 0.10.41 (DEV-028): a Platform Admin tenant tab refused for want of the customer's approval (403
// CUSTOMER_APPROVAL_REQUIRED, backend/app/support_access.py) says that support access the customer approved is needed,
// on every tab that reads a customer's data (each is a Panel fed by its resource), instead of "Your role cannot read
// this data".

const SERVER =
  "This is the customer's data. It needs support access the customer approved: configuration. Request it under " +
  "Security > Support access.";

const panel = (source: Parameters<typeof Panel>[0]["source"]) =>
  renderToStaticMarkup(
    <Panel eyebrow="AI processing" title="AI for Validation Org" source={source}>
      <p>content</p>
    </Panel>,
  );

describe("a tab that needs the customer's approval", () => {
  it("says the customer's approval is needed, with the server's words", () => {
    const html = panel({ state: "forbidden", code: CUSTOMER_APPROVAL_REQUIRED, error: SERVER });
    expect(html).toContain("The customer&#x27;s approval is needed");
    expect(html).toContain("It needs support access the customer approved: configuration.");
    expect(html).not.toContain("Your role cannot read this data");
    expect(html).not.toContain("content");
    // Without a message of its own, the same in the screen's words.
    const plain = panel({ state: "forbidden", code: CUSTOMER_APPROVAL_REQUIRED });
    expect(plain).toContain("Reading it needs support access that the customer approved");
    expect(CUSTOMER_APPROVAL_TEXT).toContain("request it under Security > Support access");
  });

  it("keeps the role message for any other refusal", () => {
    expect(panel({ state: "forbidden", code: "PERMISSION_DENIED" })).toContain("Your role cannot read this data");
  });
});
