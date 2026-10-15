import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TRIAL_VIDEOS, VIDEO_BASE, VideoCards, readyVideos } from "./videos";

describe("free-trial videos", () => {
  it("lists all fourteen videos in order", () => {
    expect(TRIAL_VIDEOS.map((video) => video.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]);
  });

  it("reads the ready videos from videos.json and leaves out anything malformed", () => {
    const ready = readyVideos({
      videos: [
        { number: 1, file: "01-welcome.mp4", poster: "01-welcome.jpg", minutes: 5.4 },
        { number: 2, file: "../secret.mp4" },
        { number: 3, file: "03-activate.mov" },
        { number: 99, file: "99-unknown.mp4" },
        { number: 4, file: "04-tour.mp4", poster: "x/04.jpg", minutes: 400 },
      ],
    });
    expect([...ready.keys()]).toEqual([1, 4]);
    expect(ready.get(4)).toEqual({ number: 4, file: "04-tour.mp4", poster: undefined, minutes: undefined });
    expect(readyVideos(null).size).toBe(0);
    expect(readyVideos({ videos: "nope" }).size).toBe(0);
  });

  it("plays a ready video without a caption track (captions are in the picture) and shows the rest as coming soon", () => {
    const ready = readyVideos({
      videos: [{ number: 1, file: "01-welcome.mp4", captions: "01-welcome.vtt", minutes: 5.4 }],
    });
    const html = renderToStaticMarkup(<VideoCards ready={ready} />);
    expect(html).toContain(`src="${VIDEO_BASE}01-welcome.mp4"`);
    expect(html).not.toContain("<track");
    expect(html).toContain("5 min");
    expect(html.match(/Coming soon/g)).toHaveLength(13);
  });
});
