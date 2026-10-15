import { useEffect, useState } from "react";
import { ArrowRight, Clock, PlayCircle } from "lucide-react";

/**
 * The free-trial video series on the website (/videos): fourteen short videos, their English captions part of the
 * picture (so no caption track is added: the browser would show the text a second time). The
 * titles and what each one teaches are listed here; which videos are ready comes from the server's video folder
 * (videos/README.md), so a finished video is published by copying its files there, without a release. A video not
 * listed there shows as coming soon.
 */
export const VIDEO_BASE = "/media/videos/";

export const TRIAL_VIDEOS: readonly { number: number; title: string; summary: string }[] = [
  {
    number: 1,
    title: "Welcome to MDARIX",
    summary: "What MDARIX does, why warning letters happen, what the 30-day trial gives you, and the quality loop.",
  },
  {
    number: 2,
    title: "Signing up for your free trial",
    summary: "From the website to a trial that is prepared for you at once.",
  },
  {
    number: 3,
    title: "Activating and securing your account",
    summary: "The activation link, your password, the authenticator app and your recovery codes.",
  },
  {
    number: 4,
    title: "Your trial workspace: a guided tour",
    summary:
      "Getting started, the nine-chapter story, what you were cited for, the journey tracker and the main screens.",
  },
  {
    number: 5,
    title: "Inviting your team",
    summary: "Adding two colleagues, how they activate, and why a second person matters.",
  },
  {
    number: 6,
    title: "Understanding the sample data",
    summary: "The fictional company in your trial, the real problems it re-creates, and why they matter to you.",
  },
  {
    number: 7,
    title: "Chapter 1: Finding hidden complaints",
    summary: "A second look at records closed as cancellations, inquiries or No Fault Found.",
  },
  {
    number: 8,
    title: "Chapter 2: Never missing a reporting deadline",
    summary: "Reporting clocks for the FDA and the EU, and recording each decision inside its window.",
  },
  {
    number: 9,
    title: "Chapter 3: From a rising trend to a case",
    summary: "The trend check, a signal, and one click from the signal to its case.",
  },
  {
    number: 10,
    title: "Chapters 4 and 5: Investigating and signing the decision",
    summary: "Evidence you can trace, the decision brief, and signing with your password and phone code.",
  },
  {
    number: 11,
    title: "Chapters 6 to 8: CAPA, risk file and the inspector pack",
    summary: "Proving a CAPA worked, feeding the risk file, and the inspection pack.",
  },
  {
    number: 12,
    title: "Bringing your own data",
    summary: "Uploading your quality system's export as it is, and seeing insights on your own records.",
  },
  {
    number: 13,
    title: "Removing the sample data",
    summary: "Switching to only your own records while your progress is kept.",
  },
  {
    number: 14,
    title: "Feedback, booking your demo and ending the trial",
    summary: "The one-click rating, a one-to-one demo, and ending the trial early with your data deleted.",
  },
];

/** A ready video, as the server's videos.json lists it: file names inside VIDEO_BASE. */
export type ReadyVideo = { number: number; file: string; poster?: string; minutes?: number };

const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

/** The ready videos in a videos.json document; anything malformed is left out rather than trusted. */
export function readyVideos(document: unknown): Map<number, ReadyVideo> {
  const ready = new Map<number, ReadyVideo>();
  const list = (document as { videos?: unknown } | null)?.videos;
  if (!Array.isArray(list)) return ready;
  for (const entry of list) {
    if (!entry || typeof entry !== "object") continue;
    const { number, file, poster, minutes } = entry as Record<string, unknown>;
    if (typeof number !== "number" || !TRIAL_VIDEOS.some((video) => video.number === number)) continue;
    if (typeof file !== "string" || !SAFE_FILE.test(file) || !file.toLowerCase().endsWith(".mp4")) continue;
    const safe = (name: unknown, ending: string) =>
      typeof name === "string" && SAFE_FILE.test(name) && name.toLowerCase().endsWith(ending) ? name : undefined;
    ready.set(number, {
      number,
      file,
      poster: safe(poster, ".jpg"),
      minutes: typeof minutes === "number" && minutes > 0 && minutes < 60 ? minutes : undefined,
    });
  }
  return ready;
}

export function VideoCards({ ready }: { ready: Map<number, ReadyVideo> }) {
  return (
    <ol className="ms-videos" aria-label="The free-trial videos">
      {TRIAL_VIDEOS.map((video) => {
        const item = ready.get(video.number);
        return (
          <li key={video.number} className={`ms-card ms-video${item ? "" : " is-soon"}`}>
            {item ? (
              <video
                controls
                preload="none"
                playsInline
                src={VIDEO_BASE + item.file}
                poster={item.poster ? VIDEO_BASE + item.poster : undefined}
                aria-label={`Video ${video.number}: ${video.title}`}
              />
            ) : (
              <div className="ms-video-soon" aria-hidden="true">
                <PlayCircle size={40} />
              </div>
            )}
            <span className="ms-eyebrow">
              Video {video.number} of {TRIAL_VIDEOS.length}
            </span>
            <strong>{video.title}</strong>
            <p>{video.summary}</p>
            {item ? (
              item.minutes && (
                <span className="ms-badge ms-badge-current">
                  <Clock size={13} aria-hidden="true" /> {Math.round(item.minutes)} min
                </span>
              )
            ) : (
              <span className="ms-badge ms-badge-future">Coming soon</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function VideosPage() {
  const [ready, setReady] = useState<Map<number, ReadyVideo>>(() => new Map());
  useEffect(() => {
    let live = true;
    fetch(VIDEO_BASE + "videos.json", { cache: "no-cache" })
      .then((response) => (response.ok ? response.json() : null))
      .then((document) => live && setReady(readyVideos(document)))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return (
    <>
      <section className="ms-page-hero ms-videos-hero">
        <div className="ms-page-hero-copy">
          <span className="ms-eyebrow">Free trial videos</span>
          <h1>MDARIX Free Trial, Step by Step</h1>
          <p>
            Fourteen short videos follow a quality manager through the 30-day free trial, from signing up to every
            chapter of the story. Each one has English captions.
          </p>
          <a className="ms-btn ms-btn-primary" href="/signup">
            Start free trial <ArrowRight size={16} aria-hidden="true" />
          </a>
        </div>
      </section>
      <section className="ms-section">
        <VideoCards ready={ready} />
      </section>
    </>
  );
}
