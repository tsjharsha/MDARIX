import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import walkthrough from "../../../../docs/user-guide/QUALITY_MANAGER_WORKFLOW_WALKTHROUGH.md?raw";
import { afterTheTrial } from "../../site/content";
import { anchorPages, capabilityCopy, pages as pageContent, solutionOverrides } from "../../site/legacyContent";
import { INDEXED_PATHS, renderPage } from "../../site/prerender";
import { questionAt } from "../../site/questions";
import { BESIDE_YOUR_QMS, PMS_FRAMING } from "./besideYourQms";
import pilotGuide from "./PILOT_GUIDE.md?raw";
import { TrialGuidePage } from "./TrialGuidePage";
import { CONNECTION, MVP_STEPS, QUESTIONS } from "./trialNextSteps";
import { UserGuidePage } from "./UserGuidePage";

// T-MSG (0.10.50): one message on what MDARIX is beside the customer's systems, the same words in every place
// (TA-MSG.1), and only what ships today (TA-MSG.2).
const text = (html: string) =>
  html
    .replace(/<script[\s\S]*?<\/script>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

describe("MDARIX works beside your QMS", () => {
  it("says what ships by 0.10.54, and claims no feature a later release ships", () => {
    expect(BESIDE_YOUR_QMS).toBe(
      "MDARIX works beside your QMS or complaint software. Your QMS keeps the complaint record, CAPA and change control. " +
        "MDARIX helps you decide and proves it: routine complaints close at service level with a documented reason, " +
        "serious ones are assessed per market, and you get signed documents to file in your QMS.",
    );
    expect(BESIDE_YOUR_QMS).not.toMatch(/proactive/i);
  });

  it("frames reactive and proactive PMS and the loop, without claiming MDARIX records proactive sources yet", () => {
    expect(PMS_FRAMING).toBe(
      "Post-market surveillance gathers data reactively, from what reaches you (complaints, service records, " +
        "incidents, field actions), and proactively, from what you go out to look for. The results feed one loop: " +
        "PMS → risk management → clinical evaluation → PSUR → back to the PMS plan.",
    );
    expect(PMS_FRAMING).not.toMatch(/MDARIX also plans|records your proactive/i);
    expect(text(renderToStaticMarkup(<TrialGuidePage />))).toContain(PMS_FRAMING);
    expect(text(renderToStaticMarkup(<UserGuidePage />))).toContain(PMS_FRAMING);
    expect(pilotGuide).toContain(PMS_FRAMING);
    expect(walkthrough).toContain(PMS_FRAMING);
  });

  it("is said in the same words on the website, the guides and the docs", () => {
    const faq = questionAt("/questions/does-mdarix-replace-our-qms")!;
    expect(faq.question).toBe("Does MDARIX replace our QMS or complaint software?");
    expect(faq.answer).toBe(`No: ${BESIDE_YOUR_QMS}`);
    expect(text(renderPage("/questions/does-mdarix-replace-our-qms"))).toContain(BESIDE_YOUR_QMS);
    expect(text(renderPage("/"))).toContain("Works beside your QMS or complaint software");
    for (const path of ["/trust", "/company"] as const) expect(text(renderPage(path)), path).toContain(BESIDE_YOUR_QMS);
    expect(text(renderToStaticMarkup(<TrialGuidePage />))).toContain(BESIDE_YOUR_QMS);
    expect(text(renderToStaticMarkup(<UserGuidePage />))).toContain(BESIDE_YOUR_QMS);
    expect(pilotGuide).toContain(BESIDE_YOUR_QMS);
    expect(walkthrough).toContain(BESIDE_YOUR_QMS);
  });

  it("keeps the decisions in MDARIX and the complaint record in your QMS, from the trial to the pilot", () => {
    const work = MVP_STEPS.find((step) => step.title === "Work on your real complaints")!;
    expect(work.text).toContain("MDARIX keeps the decisions, and your QMS keeps the complaint record.");
    expect(pilotGuide).toContain("MDARIX keeps the decisions, and your QMS keeps the complaint record.");
    const record = "Your QMS keeps the complaint record, CAPA and change control";
    for (const said of [
      CONNECTION.find((item) => item.title === "Your systems")!.text,
      QUESTIONS.find((item) => item.question === "Who owns the data?")!.answer,
      afterTheTrial.points.map(([, point]) => point).join(" "),
    ])
      expect(said).toContain(record);
  });

  it("replaces the older 'systems of record stay' wording on every page", () => {
    const places = [
      ...INDEXED_PATHS.map((path) => text(renderPage(path))),
      JSON.stringify({
        CONNECTION,
        QUESTIONS,
        afterTheTrial,
        pageContent,
        capabilityCopy,
        anchorPages,
        solutionOverrides,
      }),
      pilotGuide,
    ];
    for (const place of places) {
      // Every older variant (0.10.62): "stay the record", "remain authoritative (systems of record)".
      expect(place).not.toMatch(
        /stays? (the|your) (systems? of )?record|systems of record stay|stay where they are|(source|systems?|platforms?) remains? authoritative|authoritative systems? of record/i,
      );
      expect(place).not.toContain("Works above QMS");
    }
  });
});
