import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import trialAgreement from "../../../legal/trial-agreement.md?raw";
import { resolveSitePath } from "../PublicMegaSite";
import { trialIncludes } from "./legacyContent";
import { ResourcesPage } from "./pages";
import { renderPage } from "./prerender";
import {
  QUESTIONS,
  QUESTIONS_PATH,
  QUESTION_PATHS,
  QuestionPage,
  QuestionsPage,
  questionAt,
  questionJsonLd,
  questionsJsonLd,
} from "./questions";
import { PAGE_META, SITE_URL } from "./seo";

// The questions and answers (/questions and one page per question): the answer comes first, the page is marked up as
// FAQPage JSON-LD, and every word keeps the website's rules (no demo request, no "MVP", no warning letters, no names).
const sentences = (text: string) => text.split(/(?<=[.!?])\s+(?=[A-Z0-9])/).filter(Boolean);
const jsonLd = (html: string) =>
  [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((match) => JSON.parse(match[1]));
const textOf = (html: string) =>
  html
    .replace(/<script[\s\S]*?<\/script>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

describe("the questions and answers", () => {
  it("are an index and seven question pages, each with its own address, title and description", () => {
    expect(QUESTIONS).toHaveLength(7);
    expect(QUESTION_PATHS).toEqual(QUESTIONS.map((question) => question.path));
    expect(new Set(QUESTION_PATHS).size).toBe(7);
    for (const path of [QUESTIONS_PATH, ...QUESTION_PATHS]) {
      expect(path).toMatch(/^\/questions(\/[a-z0-9-]+)?$/);
      expect(PAGE_META[path as keyof typeof PAGE_META], path).toBeDefined();
      expect(resolveSitePath(path, ""), path).toEqual({ page: path, hash: "" });
      expect(resolveSitePath(`${path}/`, ""), path).toEqual({ page: path, hash: "" });
    }
    // A question's title is the question itself.
    for (const question of QUESTIONS)
      expect(PAGE_META[question.path as keyof typeof PAGE_META].title).toBe(`${question.question} · MDARIX`);
    expect(resolveSitePath("/questions/no-such-question", "")).toEqual({ page: "not-found", hash: "" });
  });

  it("put a direct answer of two or three sentences first, under the question as the only H1", () => {
    for (const question of QUESTIONS) {
      const html = renderToStaticMarkup(<QuestionPage question={question} />);
      expect(question.question.endsWith("?"), question.path).toBe(true);
      expect(html.match(/<h1[\s>]/g), question.path).toHaveLength(1);
      expect(html, question.path).toContain(`<h1 id="question-title">${question.question}</h1>`);
      const count = sentences(question.answer).length;
      expect(count, question.path).toBeGreaterThanOrEqual(2);
      expect(count, question.path).toBeLessThanOrEqual(3);
      // The answer is the first text after the heading; the explanation and what MDARIX does follow.
      const after = html.slice(html.indexOf("</h1>"));
      expect(after.indexOf("The short answer"), question.path).toBeLessThan(after.indexOf("<h2>"));
      expect(html, question.path).toContain(`<h2>${question.mdarix.title}</h2>`);
      expect(question.sections.length, question.path).toBeGreaterThanOrEqual(2);
      // The way on: the free trial, the other questions and the list of all of them.
      expect(html, question.path).toContain('href="/signup"');
      expect(html, question.path).toContain(`href="${QUESTIONS_PATH}"`);
      for (const other of QUESTIONS.filter((item) => item !== question))
        expect(html, question.path).toContain(`href="${other.path}"`);
    }
  });

  it("mark each page up as an FAQPage whose question and answer are the page's own words", () => {
    for (const question of QUESTIONS) {
      const html = renderToStaticMarkup(<QuestionPage question={question} />);
      const blocks = jsonLd(html);
      expect(blocks, question.path).toHaveLength(1);
      expect(blocks[0]).toEqual(questionJsonLd(question));
      expect(blocks[0]).toMatchObject({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        url: `${SITE_URL}${question.path}`,
        mainEntity: [
          {
            "@type": "Question",
            name: question.question,
            acceptedAnswer: { "@type": "Answer", text: question.answer },
          },
        ],
      });
    }
    const index = jsonLd(renderToStaticMarkup(<QuestionsPage />));
    expect(index).toEqual([questionsJsonLd()]);
    expect(index[0]["@type"]).toBe("CollectionPage");
    expect(index[0].mainEntity.itemListElement.map((item: { url: string }) => item.url)).toEqual(
      QUESTION_PATHS.map((path) => `${SITE_URL}${path}`),
    );
  });

  it("keep a JSON-LD block from ending early, whatever its text", () => {
    const question = { ...QUESTIONS[0], answer: "A </script><script>alert(1)</script> B. Second sentence." };
    const html = renderToStaticMarkup(<QuestionPage question={question} />);
    expect(html).not.toContain("<script>alert(1)");
    expect(jsonLd(html)[0].mainEntity[0].acceptedAnswer.text).toBe(question.answer);
  });

  it("are listed on the questions page, the Resources page and in the footer", () => {
    const index = renderToStaticMarkup(<QuestionsPage />);
    expect(index).toContain('<h1 id="questions-title">');
    for (const question of QUESTIONS) expect(index).toContain(`<a href="${question.path}">${question.question}</a>`);
    const resources = renderToStaticMarkup(<ResourcesPage />);
    expect(resources).toContain(`href="${QUESTIONS_PATH}"`);
    for (const question of QUESTIONS) expect(resources).toContain(`href="${question.path}"`);
    // The footer, on every website page, and the header marks Resources on a question page.
    for (const path of ["/", "/resources", QUESTIONS_PATH, QUESTION_PATHS[0]] as const)
      expect(renderPage(path), path).toContain(`<a href="${QUESTIONS_PATH}">Questions and answers</a>`);
    expect(renderPage(QUESTION_PATHS[0])).toMatch(/<a href="\/resources" class="is-current">Resources<\/a>/);
    expect(renderPage("/platform")).not.toMatch(/<a href="\/resources" class="is-current">/);
  });

  it("keep the website's rules in every word", () => {
    const pages = [
      renderToStaticMarkup(<QuestionsPage />),
      ...QUESTIONS.map((question) => renderToStaticMarkup(<QuestionPage question={question} />)),
    ];
    for (const html of pages) {
      const text = textOf(html);
      expect(html).not.toContain("/request-demo");
      expect(text).not.toMatch(/request a demo|book a demo|schedule a demo/i);
      expect(text).not.toMatch(/\bMVP\b/);
      expect(text).not.toMatch(/warning letter|class action/i);
      expect(text).not.toMatch(/founder|Telikicherla|Srinivas/i);
      // Single sign-on is planned, and MDARIX holds no certification and is not a validated (GxP) system.
      expect(text).not.toMatch(/single sign-on|\bSSO\b|certified|ISO 27001|SOC 2|GxP/i);
    }
    // The paid step after the trial is a pilot.
    expect(textOf(renderToStaticMarkup(<QuestionPage question={questionAt(QUESTION_PATHS[5])!} />))).toContain(
      "the next step is a pilot",
    );
  });

  it("say only what is true of the free trial, as the trial agreement and the website say it", () => {
    const trial = questionAt("/questions/try-complaint-trending-on-your-own-data")!;
    const text = textOf(renderToStaticMarkup(<QuestionPage question={trial} />));
    for (const item of trialIncludes) expect(text).toContain(item);
    expect(text).toContain("approved automatically and ready within minutes, up to a daily limit");
    expect(text).toContain("reviewed by the MDARIX team first, usually within one business day");
    // Since 0.10.48 a personal address is approved automatically too, and a disposable one is reviewed.
    expect(text).toContain("with a company or personal email address it is approved automatically");
    expect(text).toContain("Requests from disposable email addresses, and any beyond that limit, are reviewed");
    expect(text).not.toContain("Requests from personal email addresses are reviewed");
    expect(text).toContain("do not enter patient-identifiable data");
    expect(text).toContain("deleted 30 days after the trial ends");
    // The agreement says the same.
    for (const fact of [
      "**Length:** 30 days",
      "**Users:** up to 50 people",
      "**Data:** up to 5,000 uploaded rows",
      "approved automatically, usually within minutes, up to a daily limit",
      "so is a request from a personal email address",
      "from a disposable email address",
      "usually within one business day",
      "Do not enter patient-identifiable data",
      "deleted 30 days after the trial ends",
      "ask for your data to be deleted at the same time",
    ])
      expect(trialAgreement).toContain(fact);
  });

  it("say that a person decides reportability, that MDARIX submits nothing, and that it is not advice", () => {
    const reportable = questionAt("/questions/when-is-a-complaint-reportable")!;
    const text = textOf(renderToStaticMarkup(<QuestionPage question={reportable} />));
    expect(reportable.answer).toContain(
      "A person decides what is reportable; MDARIX keeps the clock and never submits a report.",
    );
    expect(text).toContain("general information, not legal or regulatory advice");
    for (const basis of ["21 CFR 803.50", "21 CFR 803.53", "Article 87(3)", "Article 87(4)", "Article 87(5)"])
      expect(text).toContain(basis);
    for (const window of ["30 calendar days", "5 work days", "15 days", "2 days", "10 days"])
      expect(text).toContain(window);
  });
});
