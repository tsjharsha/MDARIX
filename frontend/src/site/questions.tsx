import { ArrowRight, Check } from "lucide-react";
import { BESIDE_YOUR_QMS, WHAT_MDARIX_ADDS } from "../features/help/besideYourQms";
import { trialIncludes } from "./content";
import { SITE_URL } from "./seo";

// Questions and answers (/questions and one page per question): what medical device quality and regulatory teams ask
// about complaint trending, reportability, the risk file and CAPA, written so a search engine or an AI assistant can
// quote the answer. Each page puts a direct answer first, then a short factual explanation, then what MDARIX does about
// it, and carries the question and its answer as schema.org FAQPage JSON-LD. Regulatory statements stay general,
// conservative and exact; what MDARIX does is only what the product does today (the roadmap's "Available today",
// content.ts, the in-app user guide). Titles and descriptions are in seo.ts PAGE_META, the pages in public/sitemap.xml.

export const QUESTIONS_PATH = "/questions";

type QuestionSection = { title: string; paragraphs?: readonly string[]; points?: readonly string[] };

export type Question = {
  path: `${typeof QUESTIONS_PATH}/${string}`;
  /** The page's H1 and the FAQPage question. */
  question: string;
  /** One line for the questions list. */
  summary: string;
  /** The direct answer, two or three sentences: the first thing on the page and the FAQPage answer. */
  answer: string;
  sections: readonly QuestionSection[];
  /** What MDARIX does about it, in the free trial today. */
  mdarix: { title: string; points: readonly string[] };
  /** Said under the answer where the page states a rule: general information, not advice. */
  note?: string;
  links: readonly (readonly [label: string, href: string])[];
};

const NOT_ADVICE =
  "This page is general information, not legal or regulatory advice. Check the current official text and your own procedures before you rely on it.";

const QUESTION_LIST = [
  {
    path: "/questions/how-to-trend-medical-device-complaints",
    question: "How do I trend medical device complaints?",
    summary: "Count clusters, compare each version's rate with its own history, and use units in the field.",
    answer:
      "Count complaints for each product version, and for each problem within it, and compare a recent window, such as the last 30 days, with that version's own history instead of a fixed number. Where you know how many units are in the field, use them as the denominator, so a version shipped in growing numbers does not look like a rising trend for that reason alone. A person then reviews every rise and decides what it needs.",
    sections: [
      {
        title: "Two questions, two checks",
        paragraphs: [
          "A count rule asks whether several complaints about the same problem arrived close together, for example 3 within 30 days. A rate check asks whether a version's complaint rate is now higher than its own history. You need both: a slow rise never forms a cluster, and a cluster on its own can be chance.",
        ],
      },
      {
        title: "Trend at the level where problems show",
        paragraphs: [
          "Trending all complaints of a product together, or only by a code assigned when a complaint is closed, can hide a rise in one version or one problem. Group by product version first, then by problem code or complaint type, and count complaints from when they are received, not only once they are closed.",
        ],
      },
      {
        title: "Choose the denominator",
        paragraphs: [
          "A complaint count grows when more devices are in use, even if nothing about the device changed. With lot quantities and release dates you can compare complaints per unit in the field. Without them, compare by calendar time and keep in mind that a growing installed base can raise the count by itself.",
        ],
      },
      {
        title: "A new version has no history yet",
        paragraphs: [
          "The first months of a new version are when a design or supplier change shows, yet the version has too little history to compare with. Compare it with the version it replaced over the same length of time.",
        ],
      },
      {
        title: "Where the rules ask for it",
        points: [
          "ISO 13485:2016 clause 8.4 asks for the analysis of data, including feedback and complaints.",
          "EU MDR Article 88 asks manufacturers to report statistically significant increases in the frequency or severity of incidents that are not serious incidents, and of expected side-effects, that could have a significant impact on the benefit-risk analysis.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "A detection rule opens a signal when enough complaints about the same problem arrive within a set number of days: 3 within 30 days unless you change it.",
        "The trend check compares each product version's last 30 days with its own history (up to 180 days, never before the version's release), grouped by version, by problem code or by complaint type.",
        "Each row says Significant rise (a chance under 1% if nothing had changed, allowing for the number of groups checked at once), Higher than usual (under 5%), In line with history, or that there are too few complaints or too little history to assess.",
        "When every lot has a quantity, the expected number follows the units in the field; without quantities, and for single-use or consumable products, the check counts by calendar days and says so. A new version is compared with the version it replaced as well as with its own history, and the stronger comparison is shown. An event linked from several records counts once.",
        "The trend check is a check, never a verdict: it raises no signal on its own. A person raises a signal from a rising row and triages it.",
      ],
    },
    links: [
      ["What is the difference between a complaint signal and a trend?", "/questions/complaint-signal-vs-trend"],
      ["Regulations and standards", "/trust#markets"],
    ],
  },
  {
    path: "/questions/when-is-a-complaint-reportable",
    question: "When does a complaint become a reportable event?",
    summary: "21 CFR Part 803 and EU MDR Article 87 in brief: what is reportable, by when, and who decides.",
    answer:
      "A complaint becomes reportable when the event it describes meets a regulator's definition of a reportable event, and the reporting window runs from the day you became aware of it. In the United States, 21 CFR Part 803 asks manufacturers to report deaths, serious injuries and malfunctions that would be likely to cause or contribute to one if they recurred, within 30 calendar days; under the EU MDR, Article 87 asks for serious incidents to be reported within 15 days of awareness, and sooner in some cases. A person decides what is reportable; MDARIX keeps the clock and never submits a report.",
    sections: [
      {
        title: "United States: 21 CFR Part 803",
        points: [
          "A manufacturer reports when it becomes aware of information that reasonably suggests that one of its marketed devices may have caused or contributed to a death or serious injury, or has malfunctioned and the malfunction would be likely to cause or contribute to a death or serious injury if it were to recur (21 CFR 803.50).",
          "The report is due within 30 calendar days of becoming aware of the event (21 CFR 803.50).",
          "A report is due within 5 work days instead when an event needs remedial action to prevent an unreasonable risk of substantial harm to the public health, or when FDA has asked in writing for 5-day reports (21 CFR 803.53).",
        ],
      },
      {
        title: "European Union: MDR Article 87",
        points: [
          "A serious incident is an incident that directly or indirectly led, might have led or might lead to a death, a temporary or permanent serious deterioration of a person's state of health, or a serious public health threat (Article 2(65)).",
          "Serious incidents are reported immediately after the manufacturer has established a causal relationship with its device, or that one is reasonably possible, and no later than 15 days after becoming aware of the incident (Article 87(3)).",
          "For a serious public health threat: immediately, and no later than 2 days after becoming aware of it (Article 87(4)).",
          "For a death or an unanticipated serious deterioration in a person's state of health: immediately after a causal relationship is established or suspected, and no later than 10 days after becoming aware of the serious incident (Article 87(5)).",
        ],
      },
      {
        title: "Why the awareness date matters",
        paragraphs: [
          "Every window counts from the day you became aware, so a complaint filed in the wrong category, or reviewed late, uses up time. A complaint closed as an inquiry or as no fault found can still describe a reportable event, and a complaint that names a death or serious injury needs a reportability decision whatever its category.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "Counts each complaint's reporting windows from the day you became aware, using the windows your procedure sets. Templates for the US, EU/NI, GB, Canada and India keep their basis (21 CFR 803.50 and 803.53, EU MDR Article 87, UK MDR 2002, Canada's Medical Devices Regulations ss. 59–61, India's Medical Devices Rules 2017 with the MvPI worksheet).",
        "Shows which clocks are due, overdue or missing answers, and keeps each reportability decision with the named person who made it and their reason: reported, with the report reference and filing date, or not reportable.",
        "Brings complaints closed as inquiries or no fault found back for a second look, so a reportable event is not lost in the wrong category, and flags a death or serious injury closed without an investigation.",
        "MDARIX never decides reportability and never submits anything to a regulator: you record what was filed in the authority's own system.",
      ],
    },
    note: NOT_ADVICE,
    links: [
      ["Reporting windows for the US, EU/NI, GB, Canada and India (MvPI worksheet)", "/trust#markets"],
      ["How do I trend medical device complaints?", "/questions/how-to-trend-medical-device-complaints"],
    ],
  },
  {
    path: "/questions/post-market-data-and-the-risk-file",
    question: "How should post-market data feed the risk file?",
    summary: "ISO 14971:2019 clause 10 in brief: review field information for safety and record every risk review.",
    answer:
      "ISO 14971:2019 clause 10 asks manufacturers to collect and review information from production and post-production, complaints among it, and to judge whether it is relevant to safety. Where it is, the manufacturer reviews the risk management file to decide whether risks need to be reassessed or new risks assessed, and whether action is needed for devices already on the market. In practice, every trend, complaint cluster and investigation finding should end in a recorded risk review, even when the answer is that the risk file stays as it is.",
    sections: [
      {
        title: "What clause 10 asks for",
        points: [
          "A system to actively collect and review information about the device in production and post-production.",
          "A review of that information for possible relevance to safety: for example a hazard or hazardous situation not recognized before, an estimated risk that is no longer acceptable, or an overall residual risk that is no longer acceptable in relation to the benefits.",
          "Where the information is relevant to safety, a review of the risk management file, a decision on whether risks must be reassessed or new risks assessed, and consideration of action for devices already on the market.",
        ],
      },
      {
        title: "Make the link explicit",
        paragraphs: [
          "Post-market data reaches the risk file only if someone connects it: each complaint and failure mode to the hazards, risks and risk controls it touches. A trend that nobody compared with the risk file, or a risk review that left no record, is a gap even when the risk estimate would not have changed.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "Links complaints and failure modes to the risks and controls they touch, so field signals reach the risk file. Risks come in with the CSV templates, like products, lots and complaints.",
        "Readiness checks name the post-market data not yet in the risk file, and the trends with no CAPA or risk review, each opening the records behind it.",
        "Lets you plan and sign the CAPA effectiveness check, send input to the risk file, and download the inspector summary as one pack.",
        "MDARIX does not replace your risk management file: a person decides what the risk file must say, and the risk file stays in your QMS.",
      ],
    },
    note: NOT_ADVICE,
    links: [
      ["How do I show a CAPA was effective?", "/questions/show-capa-effectiveness"],
      ["ISO 14971 and the other standards", "/trust#markets"],
    ],
  },
  {
    path: "/questions/complaint-signal-vs-trend",
    question: "What is the difference between a complaint signal and a trend?",
    summary: "A trend is a measurement over time; a signal is an observation a person triages.",
    answer:
      "A trend is a measurement: how the rate of complaints for a product, version or problem changes over time compared with its history. A signal is a recorded observation that something may need attention, such as a cluster of similar complaints or a rate above its history, which a person then triages. A trend can lead to a signal, but neither is a conclusion about cause.",
    sections: [
      {
        title: "A trend is always there",
        paragraphs: [
          "Every product version has a complaint rate at any time, whether anyone looks at it or not. A trend analysis compares that rate with what came before and says whether it is in line, higher, or too thin to judge.",
        ],
      },
      {
        title: "A signal has an owner",
        paragraphs: [
          "A signal is an item someone must act on: it has its complaints, a priority, an owner and a decision, such as investigate, escalate, monitor until a review date, or no action needed, with the reason recorded. Closing a signal is a decision; a trend line is not.",
        ],
      },
      {
        title: "Why the difference matters",
        paragraphs: [
          "The trend shows that the data was analysed; the signal's triage shows what was done about it. A rising trend that never became a signal, or a signal closed without looking at the trend, leaves a gap in the record. The words are used differently between companies and regulations, so write down in your procedure what each one means for you.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "The Signal inbox holds every signal with its complaints, what they have in common (each point linked to its complaints) and its trend check.",
        "Triage records the priority and the disposition (investigation required, escalate, monitor with a date to review again, no action needed, or a duplicate of another signal) with a reason, in the signal's history and the audit trail.",
        "The trend check compares each version's complaint rate with its own history; it raises no signal on its own, and a person raises one from a rising row.",
        "Readiness names the signals waiting past their triage date, and a case opens from a signal in one click with every complaint.",
      ],
    },
    links: [
      ["How do I trend medical device complaints?", "/questions/how-to-trend-medical-device-complaints"],
      ["Investigations on the Platform", "/platform#investigations"],
    ],
  },
  {
    path: "/questions/show-capa-effectiveness",
    question: "How do I show a CAPA was effective?",
    summary: "Set the criteria before the action, measure from the right date, and sign what you found.",
    answer:
      "Decide, when you plan the action, what will show that it worked, from which date you will measure and when you will check; then check against those criteria and record the result with the evidence you saw. For a CAPA opened from complaints, that evidence is often whether the same problem recurred on the affected product after the action, compared with before. ISO 13485:2016 clause 8.5.2 asks for the effectiveness of corrective action to be reviewed: closing a CAPA is not the same as showing it worked.",
    sections: [
      {
        title: "Set the criteria first",
        paragraphs: [
          "Write down what will show the action worked before you see the result, in terms someone else can check: for example, no complaint with the same problem code on lots built after the change, over a period long enough to have seen the problem had it continued.",
        ],
      },
      {
        title: "Measure from when the action took effect",
        paragraphs: [
          "Start the measurement when the action reached the product, such as the first lot built after a change, not when the CAPA was approved. Compare like with like: the same product and the same problem codes, before and after.",
        ],
      },
      {
        title: "Record the judgement",
        paragraphs: [
          "The result is a judgement against the criteria, made and signed by an authorized person, with what they saw. If the action did not work, the record says so and leads to a further action.",
        ],
      },
      {
        title: "Where the rules ask for it",
        points: [
          "ISO 13485:2016 clause 8.5.2 (corrective action) and clause 8.5.3 (preventive action) include reviewing the effectiveness of the action taken.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "Every CAPA that is not cancelled or rejected gets an effectiveness check, closed ones included, and you can filter the checks that are overdue, due soon or not planned.",
        "You plan the check: what will show the action worked, the day measurement starts and the day to check. Quality reviewers get a reminder 14 days before the check day.",
        "The check shows complaint recurrence on the CAPA's product and problem codes before and since the action, as observed counts, not a statistical verdict.",
        "An authorized person signs the result, Effective or Not effective, with what they found, their password and an authenticator code. Readiness names the CAPAs without a verified effect.",
      ],
    },
    links: [
      ["How should post-market data feed the risk file?", "/questions/post-market-data-and-the-risk-file"],
      ["Signed decisions on the Platform", "/platform#decisions"],
    ],
  },
  {
    path: "/questions/try-complaint-trending-on-your-own-data",
    question: "Can I try complaint trending on my own data without a demo call?",
    summary: "Yes: a free 30-day trial, requested on the website, with sample data first and then your own exports.",
    answer:
      "Yes. You request the MDARIX free 30-day trial on the website, with no demo call and no credit card; with a company or personal email address it is approved automatically and ready within minutes, up to a daily limit. Your workspace starts with sample data, and you can then import your own complaint, product and lot exports, up to 5,000 rows, and see the signals and trend checks on your own data.",
    sections: [
      {
        title: "What the trial includes",
        points: trialIncludes,
      },
      {
        title: "How a request is approved",
        paragraphs: [
          "A request from a company or personal email address is approved automatically, usually within minutes, up to a daily limit of new trials. Requests from disposable email addresses, and any beyond that limit, are reviewed by the MDARIX team first, usually within one business day.",
        ],
      },
      {
        title: "Your data in the trial",
        points: [
          "Imports are CSV or Excel with your own column names, guided by templates. Every file is checked for problems and personal data before import, and personal details are refused or replaced before anything is stored.",
          "Use sample data, or data that does not identify patients: do not enter patient-identifiable data during the trial.",
          "Your trial workspace and everything in it are deleted 30 days after the trial ends. You can ask to end the trial early from the workspace, and ask for your data to be deleted at the same time.",
        ],
      },
      {
        title: "To see trends on your own data",
        paragraphs: [
          "Import several months of complaints: the trend check needs at least 60 days of a version's history and 3 recent complaints to assess it. Add lot quantities to count complaints per unit in the field from the first day.",
        ],
      },
    ],
    mdarix: {
      title: "After the trial",
      points: [
        "When the trial has shown how MDARIX works, the next step is a pilot: MDARIX working on your real complaints, connected to your own systems, priced in a written proposal.",
      ],
    },
    links: [
      ["Free trial agreement", "/trial-agreement"],
      ["Privacy policy", "/privacy"],
      ["Free trial videos", "/videos"],
    ],
  },
  {
    path: "/questions/does-mdarix-replace-our-qms",
    question: "Does MDARIX replace our QMS or complaint software?",
    summary: "No. MDARIX works beside it, and your QMS keeps the complaint record, CAPA and change control.",
    answer: `No: ${BESIDE_YOUR_QMS}`,
    sections: [
      {
        title: "What stays in your QMS",
        paragraphs: [
          "Complaints are logged and closed in your QMS or complaint software, and CAPA and change control run there. MDARIX never changes your records in it.",
        ],
      },
      {
        title: "What MDARIX adds",
        paragraphs: [WHAT_MDARIX_ADDS],
      },
      {
        title: "How your data gets in",
        paragraphs: [
          "In the free trial you upload CSV or Excel exports of your complaints, products and lots. In a pilot, your systems are connected through an approved mapping file and refreshed on a schedule.",
        ],
      },
    ],
    mdarix: {
      title: "What MDARIX does",
      points: [
        "Opens a signal when complaints about the same problem cluster, and compares each product version's complaint rate with its own history.",
        "Brings complaints closed as inquiries or no fault found back for a second look.",
        "Keeps each complaint's reporting clock, and each reportability decision with the named person who made it and their reason.",
        "Keeps each decision with its evidence and the named person who signed it.",
        "MDARIX never decides for you and never submits a report: you file every report in the authority's own system.",
      ],
    },
    links: [
      ["Integration approach", "/trust#integrations"],
      ["Free trial videos", "/videos"],
    ],
  },
] as const satisfies readonly Question[];

export const QUESTIONS: readonly Question[] = QUESTION_LIST;
export type QuestionPath = (typeof QUESTION_LIST)[number]["path"];
export const QUESTION_PATHS = QUESTION_LIST.map((item) => item.path);

export const questionAt = (path: string) => QUESTIONS.find((item) => item.path === path);

/** A page's JSON-LD: one question and its direct answer (FAQPage), the same words the page shows first. */
export function questionJsonLd(question: Question) {
  return {
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
  };
}

/** The questions page's JSON-LD: the list of question pages. The answers are marked up once, on their own pages. */
export function questionsJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "Questions and answers",
    url: `${SITE_URL}${QUESTIONS_PATH}`,
    mainEntity: {
      "@type": "ItemList",
      itemListElement: QUESTIONS.map((item, index) => ({
        "@type": "ListItem",
        position: index + 1,
        name: item.question,
        url: `${SITE_URL}${item.path}`,
      })),
    },
  };
}

/** Structured data as a JSON-LD block. It is data, not a script: browsers never run it, so the CSP (script-src
 * 'self') allows it, as it allows the organization's block in index.html. "<" is escaped so no text can end it. */
function JsonLd({ data }: { data: object }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}

function TrialBox() {
  return (
    <aside className="ms-question-trial" aria-label="Free trial">
      <strong>Try it on your own data</strong>
      <p>A free 30-day trial for up to 50 people, with sample data first and then your own exports. No credit card.</p>
      <a className="ms-btn ms-btn-primary" href="/signup">
        Start free trial <ArrowRight size={16} aria-hidden="true" />
      </a>
    </aside>
  );
}

function Breadcrumb({ onQuestion = false }: { onQuestion?: boolean }) {
  return (
    <nav className="ms-breadcrumb" aria-label="Breadcrumb">
      <a href="/">Home</a>
      <span aria-hidden="true">›</span>
      {onQuestion ? <a href={QUESTIONS_PATH}>Questions and answers</a> : <span>Questions and answers</span>}
    </nav>
  );
}

export function QuestionsPage() {
  return (
    <article className="ms-section ms-legal ms-questions" aria-labelledby="questions-title">
      <Breadcrumb />
      <span className="ms-eyebrow">Questions and answers</span>
      <h1 id="questions-title">Questions about complaint trending, reporting and CAPA</h1>
      <p className="ms-legal-lead">
        Direct answers to questions medical device quality and regulatory teams ask about trending complaints,
        reportability, the risk file and CAPA, each with what MDARIX does about it. General information, not legal or
        regulatory advice.
      </p>
      <ol className="ms-question-list">
        {QUESTIONS.map((item) => (
          <li key={item.path}>
            <h2>
              <a href={item.path}>{item.question}</a>
            </h2>
            <p>{item.summary}</p>
          </li>
        ))}
      </ol>
      <TrialBox />
      <JsonLd data={questionsJsonLd()} />
    </article>
  );
}

export function QuestionPage({ question }: { question: Question }) {
  const others = QUESTIONS.filter((item) => item.path !== question.path);
  return (
    <article className="ms-section ms-legal ms-question" aria-labelledby="question-title">
      <Breadcrumb onQuestion />
      <span className="ms-eyebrow">Questions and answers</span>
      <h1 id="question-title">{question.question}</h1>
      <section className="ms-answer" aria-label="The short answer">
        <strong>The short answer</strong>
        <p>{question.answer}</p>
      </section>
      {question.note && <p className="ms-legal-note">{question.note}</p>}
      <div className="ms-legal-body">
        {question.sections.map((section) => (
          <section key={section.title}>
            <h2>{section.title}</h2>
            {section.paragraphs?.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
            {section.points && (
              <ul>
                {section.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
        <section className="ms-question-mdarix">
          <h2>{question.mdarix.title}</h2>
          <ul className="ms-check-list">
            {question.mdarix.points.map((point) => (
              <li key={point}>
                <Check size={16} aria-hidden="true" />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <TrialBox />
      <nav className="ms-question-more" aria-label="Read further">
        <h2>Read further</h2>
        <ul>
          {question.links.map(([label, href]) => (
            <li key={href}>
              <a href={href}>{label}</a>
            </li>
          ))}
          {others
            .filter((item) => !question.links.some(([, href]) => href === item.path))
            .map((item) => (
              <li key={item.path}>
                <a href={item.path}>{item.question}</a>
              </li>
            ))}
        </ul>
        <a className="ms-link" href={QUESTIONS_PATH}>
          All questions <ArrowRight size={14} aria-hidden="true" />
        </a>
      </nav>
      <JsonLd data={questionJsonLd(question)} />
    </article>
  );
}
