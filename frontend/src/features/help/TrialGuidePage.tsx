import { ArrowLeft, BookOpen, CheckCircle2, Clock3, Download, Lightbulb } from "lucide-react";
import { AFTER_THE_TRIAL, GUIDE_STEPS, TRIAL_FACTS } from "./trialGuide";
import { GuideScene, JourneyHero } from "./TrialGuideVisuals";
import "./trialGuide.css";

/**
 * The free trial user guide at /help/trial-guide: the journey from the first visit to the one-to-one demo, one step at
 * a time, each with a picture of the screen it happens on. It holds no organization data, so it opens without a
 * session: it can be read before the first sign-in, linked from the sign-up confirmation and Getting started, and
 * saved as a PDF (the browser's print) to attach to an email.
 */
export function TrialGuidePage() {
  return (
    <div className="help-page tg-page">
      <a className="app-skip" href="#help-main">
        Skip to content
      </a>
      <header className="help-page-top">
        <a className="auth-brand" href="/" aria-label="MDARIX website">
          <span className="auth-logo" aria-hidden="true">
            M
          </span>
          MDARIX
        </a>
        <span className="tg-top-actions">
          <button type="button" className="tg-print" onClick={() => window.print()}>
            <Download size={15} aria-hidden="true" /> Save as PDF
          </button>
          <a className="help-back" href="/app">
            <ArrowLeft size={15} aria-hidden="true" /> Open MDARIX
          </a>
        </span>
      </header>
      <main id="help-main" tabIndex={-1}>
        <section className="tg-hero">
          <p className="help-eyebrow tg-eyebrow">
            <BookOpen size={15} aria-hidden="true" /> Free trial user guide
          </p>
          <h1>Your MDARIX free trial, step by step</h1>
          <p className="tg-lede">
            Seven steps take you from the first visit to a one-to-one demo on your own trial: request it, sign in, bring
            two colleagues, see the sample data tell the story, run the same checks on your own export, tell us what you
            think, and book the demo.
          </p>
          <JourneyHero titles={GUIDE_STEPS.map((step) => step.title)} />
          <ul className="tg-facts" aria-label="The free trial">
            {TRIAL_FACTS.map(([value, label]) => (
              <li key={value}>
                <strong>{value}</strong>
                <span>{label}</span>
              </li>
            ))}
          </ul>
        </section>

        <nav className="tg-contents" aria-label="Steps">
          <ol>
            {GUIDE_STEPS.map((step, index) => (
              <li key={step.key}>
                <a href={`#step-${index + 1}`}>
                  <span>{index + 1}</span> {step.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="tg-steps">
          {GUIDE_STEPS.map((step, index) => (
            <section
              key={step.key}
              id={`step-${index + 1}`}
              className="tg-step"
              aria-labelledby={`step-${index + 1}-title`}
            >
              <div className="tg-step-picture">
                <GuideScene step={step.key} />
              </div>
              <div className="tg-step-text">
                <p className="tg-step-number">
                  Step {index + 1} of {GUIDE_STEPS.length}
                  <span>
                    <Clock3 size={13} aria-hidden="true" /> {step.time}
                  </span>
                </p>
                <h2 id={`step-${index + 1}-title`}>{step.title}</h2>
                <p className="tg-why">{step.why}</p>
                <ol className="tg-actions">
                  {step.actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
                <p className="tg-result">
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <span>
                    <b>You will see:</b> {step.result}
                  </span>
                </p>
                {step.tip && (
                  <p className="tg-tip">
                    <Lightbulb size={16} aria-hidden="true" />
                    <span>{step.tip}</span>
                  </p>
                )}
              </div>
            </section>
          ))}
        </div>

        <section className="tg-after" aria-labelledby="tg-after-title">
          <h2 id="tg-after-title">When the 30 days are over</h2>
          <ul>
            {AFTER_THE_TRIAL.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="tg-small">
            The pictures in this guide are illustrations of the screens; names and numbers in them are examples.
          </p>
        </section>
      </main>
    </div>
  );
}
