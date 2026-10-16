import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { AskMdarixPage } from "./AskMdarixPage";
import { handQuestionToAsk, onQuestionHanded, pendingQuestion, takeQuestion } from "./pendingQuestion";

const QUESTION = "What changed in OrbitCare 300 Infusion Pump (Sample) Rev B?";
const box = (html: string) => html.match(/<textarea[^>]*id="ask-question"[^>]*>([^<]*)<\/textarea>/)?.[1];

afterEach(() => takeQuestion(pendingQuestion()));

describe("a question handed to Ask MDARIX", () => {
  it("opens Ask MDARIX with the question in the box, not sent", () => {
    handQuestionToAsk(`  ${QUESTION}  `);
    const html = renderToStaticMarkup(<AskMdarixPage />);
    expect(box(html)).toBe(QUESTION);
    expect(html).toContain(">Ask MDARIX</button>");
    expect(html).not.toContain("MDARIX answer");
  });

  it("is taken once: coming back to Ask later shows an empty box", () => {
    handQuestionToAsk(QUESTION);
    expect(pendingQuestion()).toBe(QUESTION);
    takeQuestion(QUESTION);
    expect(pendingQuestion()).toBeNull();
    expect(box(renderToStaticMarkup(<AskMdarixPage />))).toBe("");
  });

  it("keeps a newer question when an older one is taken, and ignores an empty one", () => {
    handQuestionToAsk("First question?");
    handQuestionToAsk("Second question?");
    takeQuestion("First question?");
    expect(pendingQuestion()).toBe("Second question?");
    takeQuestion("Second question?");
    handQuestionToAsk("   ");
    expect(pendingQuestion()).toBeNull();
  });

  it("reaches an Ask page already open", () => {
    const heard: string[] = [];
    const stop = onQuestionHanded((question) => heard.push(question));
    handQuestionToAsk(QUESTION);
    stop();
    handQuestionToAsk("Not heard?");
    expect(heard).toEqual([QUESTION]);
  });
});
