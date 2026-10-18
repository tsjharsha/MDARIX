import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Chip, MAX_FLOOR, MIN_SCALED_PX, MIN_TEXT_PX, Scene, chipWidth, textFloor } from "./kit";

// The canvas size a label of `floor` units renders at on screen, in a frame width×height drawn at page zoom `zoom`.
const onScreen = (floor: number, width: number, height: number, zoom = 1) =>
  floor * Math.min(width / 640, height / 400) * zoom;

describe("scene text floor", () => {
  it("keeps labels at 13 px on screen at 100% and 12 px under the 80% and 90% page scale", () => {
    // The usual section picture (647×404 CSS px), at 100%, 90% and 80%.
    expect(textFloor(647, 404)).toBe(12.9);
    expect(textFloor(647, 404, 0.9)).toBe(13.3);
    expect(textFloor(647, 404, 0.8)).toBe(14.9);
    for (const zoom of [1, 0.9, 0.8]) {
      const px = onScreen(textFloor(647, 404, zoom), 647, 404, zoom);
      expect(px).toBeGreaterThanOrEqual(zoom === 1 ? MIN_TEXT_PX : MIN_SCALED_PX);
    }
  });

  it("never asks a layout for more than MAX_FLOOR", () => {
    expect(MAX_FLOOR).toBe(16);
    // The scenes two to a row on Solutions (527×329): 15.9 at 100% (13 px), capped at 80%.
    expect(textFloor(527, 329)).toBe(15.9);
    expect(textFloor(527, 329, 0.8)).toBe(MAX_FLOOR);
    // A narrow window (a 492 px frame) and the Trust hero at 80% (625×391 → 15.4).
    expect(textFloor(492, 308)).toBe(MAX_FLOOR);
    expect(textFloor(625, 391, 0.8)).toBe(15.4);
    for (const width of [480, 520, 600, 640, 760, 976, 1500])
      for (const zoom of [1, 0.9, 0.8]) expect(textFloor(width, width / 1.6, zoom)).toBeLessThanOrEqual(MAX_FLOOR);
  });

  it("lowers the floor as the frame grows, and leaves the scenes' own sizes to phone frames and unmeasured ones", () => {
    expect(textFloor(976, 610)).toBe(8.6);
    expect(textFloor(1500, 938)).toBeLessThan(textFloor(976, 610));
    expect(textFloor(342, 214)).toBe(13);
    expect(textFloor(0, 0)).toBe(0);
  });
});

describe("chips", () => {
  it("are wide enough for their label at the floor, and end where align puts them", () => {
    expect(chipWidth("Advises only", 16)).toBeCloseTo(12 * 16 * 0.54 + 24);
    expect(chipWidth("Rev A", 16, 76)).toBe(76);
    const html = renderToStaticMarkup(
      <Scene label="chips">
        <Chip x={578} y={23} align="end" text="Rev B in focus" />
      </Scene>,
    );
    // Before the frame is measured the floor is 0, so the chip is sized for 12 px text and ends at x = 578.
    const w = chipWidth("Rev B in focus", 0);
    expect(html).toContain(`translate(${578 - w / 2} 23)`);
  });
});
