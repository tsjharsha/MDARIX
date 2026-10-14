import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { formatBits, qrCode, reedSolomonDivisor, reedSolomonRemainder, versionFor } from "./qrCode";
import { QrCodeSvg } from "./QrCodeSvg";

describe("QR code", () => {
  it("writes the standard's format information for level M and each mask", () => {
    // ISO/IEC 18004 table: level M, masks 0 to 7.
    const expected = [
      "101010000010010",
      "101000100100101",
      "101111001111100",
      "101101101001011",
      "100010111111001",
      "100000011001110",
      "100111110010111",
      "100101010100000",
    ];
    expected.forEach((bits, mask) => expect(formatBits(mask).toString(2).padStart(15, "0")).toBe(bits));
  });

  it("computes Reed-Solomon codewords as the published HELLO WORLD example (version 1-M)", () => {
    const data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17];
    expect(reedSolomonRemainder(data, reedSolomonDivisor(10))).toEqual([196, 35, 39, 119, 235, 215, 231, 226, 93, 23]);
  });

  it("chooses the smallest version that holds the text, up to version 10", () => {
    expect(versionFor("HELLO")).toBe(1);
    expect(versionFor("x".repeat(122))).toBe(7);
    expect(versionFor("x".repeat(123))).toBe(8);
    expect(versionFor("x".repeat(213))).toBe(10);
    expect(versionFor("x".repeat(214))).toBeNull();
    expect(qrCode("x".repeat(214))).toBeNull();
  });

  it("draws the finder, timing and dark modules where readers look for them", () => {
    const text = "otpauth://totp/MDARIX:quality.lead%40acme.example?secret=JBSWY3DPEHPK3PXP&issuer=MDARIX";
    const grid = qrCode(text) as boolean[][];
    const size = grid.length;
    expect(size).toBe((versionFor(text) as number) * 4 + 17);
    // The top-left finder: a dark 7x7 ring, a light ring, a dark 3x3 centre.
    const finder = [0, 1, 2, 3, 4, 5, 6].map((y) => [0, 1, 2, 3, 4, 5, 6].map((x) => grid[y][x]));
    expect(finder[0].every(Boolean) && finder[6].every(Boolean)).toBe(true);
    expect(finder[1].slice(1, 6).every((cell) => !cell)).toBe(true);
    expect(finder[3].slice(2, 5).every(Boolean)).toBe(true);
    // Timing patterns alternate between the finders; the dark module sits beside the bottom-left finder.
    for (let i = 8; i < size - 8; i++) {
      expect(grid[6][i]).toBe(i % 2 === 0);
      expect(grid[i][6]).toBe(i % 2 === 0);
    }
    expect(grid[size - 8][8]).toBe(true);
  });

  it("is drawn as an SVG with a quiet zone, or not at all when the text is too long", () => {
    const html = renderToStaticMarkup(<QrCodeSvg text="HELLO" label="Setup code" />);
    expect(html).toContain('aria-label="Setup code"');
    expect(html).toContain('viewBox="0 0 29 29"'); // 21 modules and 4 on each side
    expect(renderToStaticMarkup(<QrCodeSvg text={"x".repeat(300)} label="Too long" />)).toBe("");
  });
});
