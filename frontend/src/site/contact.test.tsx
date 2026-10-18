import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ContactPage, ContactView, PUBLISHED_CONTACT, contactAddresses, type SiteInfo } from "./legal";
import privacyText from "../../../legal/privacy.md?raw";
import termsText from "../../../legal/terms.md?raw";

const info = (support: string | null, privacy: string | null): SiteInfo => ({
  company_name: "MDARIX",
  company_address: null,
  support_email: support,
  privacy_email: privacy,
  legal_text_approved: true,
  trial: { days: 30, users: 3, rows: 5000, data_deleted_after_days: 30 },
});

const NOTICE = "Contact details are being configured";

describe("contact page", () => {
  it("shows no notice and no address while the site details are loading", () => {
    // Server rendering never runs the request: this is the page as it first draws.
    const html = renderToStaticMarkup(<ContactPage />);
    expect(html).not.toContain(NOTICE);
    expect(html).not.toContain("mailto:");
    expect(contactAddresses({ status: "loading" })).toEqual({ support: null, privacy: null, notice: false });
  });

  it("falls back to the published addresses when the site details cannot be reached", () => {
    const html = renderToStaticMarkup(<ContactView state={{ status: "failed" }} />);
    expect(html).not.toContain(NOTICE);
    expect(html).toContain('href="mailto:support@mdarix.in"');
    expect(html).toContain('href="mailto:privacy@mdarix.in"');
    expect(html).toContain("Support and sales");
    // The addresses are the ones the approved legal texts publish.
    expect(privacyText).toContain(PUBLISHED_CONTACT.privacy);
    expect(termsText).toContain(PUBLISHED_CONTACT.support);
  });

  it("shows the server's addresses, and the notice only when it has neither", () => {
    const both = renderToStaticMarkup(
      <ContactView state={{ status: "ready", info: info("help@example.test", "data@example.test") }} />,
    );
    expect(both).toContain("mailto:help@example.test");
    expect(both).toContain("mailto:data@example.test");
    expect(both).not.toContain(NOTICE);
    const one = renderToStaticMarkup(
      <ContactView state={{ status: "ready", info: info("help@example.test", null) }} />,
    );
    expect(one).not.toContain(NOTICE);
    expect(one).not.toContain("Privacy and data requests</strong><a");
    const none = renderToStaticMarkup(<ContactView state={{ status: "ready", info: info(null, " ") }} />);
    expect(none).toContain(NOTICE);
    expect(none).not.toContain("mailto:");
  });

  it("keeps one card for support and sales, with no separate sales address", () => {
    const html = renderToStaticMarkup(<ContactView state={{ status: "failed" }} />);
    expect(html.match(/Support and sales/g)).toHaveLength(1);
    expect(html).not.toContain("sales@");
  });
});
