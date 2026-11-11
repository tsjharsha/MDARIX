import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BASIS_DISCLAIMER, SIGNATURE_BASIS, STANDARDS, basisOf, cite, standardOf } from "./standards";
import { BasisChips, BasisLine, BasisNote, SignatureBasis } from "./Basis";
import { TREND_BASIS } from "../workspace/signalAi";
import { EFFECTIVENESS_BASIS } from "../workspace/effectiveness";
import { SAMPLE_PAINS } from "../workspace/sampleStory";

// The screens' source as text (Vite's ?raw), to check that no screen claims compliance or certification.
const SOURCES = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

describe("the catalog of standards", () => {
  it("is the backend's catalog (tests/test_standards_unit.py keeps the two identical)", () => {
    expect(STANDARDS).toHaveLength(38);
    expect(STANDARDS.filter((standard) => standard.starter).map((standard) => standard.id)).toEqual([
      "ISO13485_6_2",
      "ISO13485_8_2_1",
      "ISO13485_8_2_2",
      "CFR803_3",
      "CFR803_19",
      "CFR803_30",
      "CFR803_40",
      "MDR_2",
      "MDR_89",
      "IVDR_82",
      "IVDR_84",
      "MDCG_2023_3",
      "IN_MDR",
      "IMDRF_GHTF_COMMON",
    ]);
    expect(new Set(STANDARDS.map((standard) => standard.id)).size).toBe(STANDARDS.length);
    expect(standardOf("CA_MDR")).toEqual({
      id: "CA_MDR",
      short: "SOR/98-282 ss. 59–61",
      title: "Mandatory problem reporting (Canada)",
      jurisdiction: "Canada",
    });
    expect(BASIS_DISCLAIMER).toBe(
      "MDARIX organizes the evidence these ask for; it does not certify compliance. Your quality system and its validation stay yours.",
    );
  });

  it("reads ids once each and cites by the short form, other parts as written", () => {
    expect(basisOf(["MDR_88", "NOPE", "MDR_88"]).map((standard) => standard.short)).toEqual(["EU MDR Art. 88"]);
    expect(basisOf(undefined)).toEqual([]);
    expect(cite("ISO13485_8_4", "MDR_88")).toBe("ISO 13485 8.4; EU MDR Art. 88");
    expect(cite("21 CFR 803", "MDR_87")).toBe("21 CFR 803; EU MDR Art. 87");
  });

  it("builds the sample story's references from it", () => {
    const references = Object.fromEntries(SAMPLE_PAINS.map((pain) => [pain.key, pain.reference]));
    expect(references).toEqual({
      routine: "ISO 13485 8.2.2",
      flagship: "21 CFR 803",
      calls: "ISO 13485 8.2.1; ISO 13485 8.2.2",
      reports: "ISO 13485 8.2.3; 21 CFR 803.50; India MDR 2017 Rules 3, 26",
      "follow-through": "ISO 13485 8.2.2",
      "lot-impact": "ISO 13485 8.5.2",
      imports: "ISO 13485 4.2.5",
      hidden: "ISO 13485 8.2.2; 21 CFR 820 (QMSR)",
      clocks: "21 CFR 803; EU MDR Art. 87",
      "harm-closed": "ISO 13485 8.2.2",
      trend: "ISO 13485 8.4; EU MDR Art. 88",
      investigate: "ISO 13485 8.2.2; ISO 13485 8.5.2",
      capa: "ISO 13485 8.5.2",
      risk: "ISO 14971 clause 10",
    });
  });
});

describe("a basis on screen", () => {
  it("shows chips with their titles, and nothing without a basis", () => {
    const markup = renderToStaticMarkup(<BasisChips ids={["ISO13485_8_5_2"]} />);
    expect(markup).toContain('role="list" aria-label="Basis"');
    expect(markup).toContain('title="Corrective action">ISO 13485 8.5.2<');
    expect(renderToStaticMarkup(<BasisChips ids={[]} />)).toBe("");
    expect(renderToStaticMarkup(<BasisNote />)).toContain(BASIS_DISCLAIMER);
  });

  it("names the trend check's and the CAPA board's basis with the disclaimer", () => {
    const trend = renderToStaticMarkup(<BasisLine ids={TREND_BASIS} />);
    expect(trend).toContain(">ISO 13485 8.4<");
    expect(trend).toContain(">EU MDR Art. 88<");
    expect(trend).toContain(BASIS_DISCLAIMER);
    const capa = renderToStaticMarkup(<BasisLine ids={EFFECTIVENESS_BASIS} />);
    expect(capa).toContain(">ISO 13485 8.5.2<");
    expect(capa.split(BASIS_DISCLAIMER).length).toBe(2);
  });

  it("says what a signed record keeps without claiming the signer's name or compliance", () => {
    const markup = renderToStaticMarkup(<SignatureBasis />);
    expect(SIGNATURE_BASIS).toBe(
      "Records, as 21 CFR 11.50 and 11.70 call for, the date and time of signing, its meaning, and a link to the exact record signed.",
    );
    expect(markup).toContain(SIGNATURE_BASIS);
    expect(markup).toContain(BASIS_DISCLAIMER);
    expect(SIGNATURE_BASIS).not.toContain("name");
  });

  it("is said where signed records are shown, and no screen claims compliance", () => {
    for (const file of [
      "../workspace/sections/DecisionRecord.tsx",
      "../workspace/sections/Records.tsx",
      "../workspace/sections/AuditTab.tsx",
      "../signature/SignatureVerificationWorkspace.tsx",
    ])
      expect(SOURCES[file], file).toContain("<SignatureBasis />");
    for (const [file, text] of Object.entries(SOURCES)) {
      expect(text, file).not.toMatch(/Part 11 compliant|compliant with (21 CFR|ISO|the EU MDR)/i);
    }
  });
});
