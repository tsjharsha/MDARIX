import { lazy, Suspense, useEffect, type ComponentType, type ReactNode } from "react";
import { PublicMegaSite } from "../PublicMegaSite";
import { applyPageMeta, applyPrivatePageMeta } from "../site/seo";
import { NewVersionNotice } from "../features/shared/NewVersionNotice";
import { SignupPage } from "../features/auth/SignupPage";
import { DEMO_REQUESTS_OFFERED } from "../site/offer";
import { TRIAL_GUIDE_PATH, USER_GUIDE_PATH } from "../features/help/paths";

// The website and the trial sign-up page are in the first script, so a pre-rendered page is replaced by the same
// page at once, with no loading state in between (WEB-05, WEB-06). Everything else loads only on its own address:
// the signed-in application (the workspace and both consoles), sign-in and the other account pages, the help guides
// and the demo request.
const RELOADED_FOR = "mdarix.reloadedForScript";

/** A screen whose script loads on first use. When the script cannot be fetched (a new release replaced it, or the
 * connection dropped), the page reloads once to fetch the current one; a second failure shows the error page. */
function lazyPage<P extends object>(load: () => Promise<ComponentType<P>>) {
  return lazy(() =>
    load().then(
      (component) => {
        try {
          sessionStorage.removeItem(RELOADED_FOR);
        } catch {
          // Storage may be off; nothing to clear then.
        }
        return { default: component };
      },
      (error: unknown) => {
        let first = true;
        try {
          first = sessionStorage.getItem(RELOADED_FOR) !== window.location.pathname;
          sessionStorage.setItem(RELOADED_FOR, window.location.pathname);
        } catch {
          // Without storage a reload cannot be told from the first try: show the error rather than reload forever.
          first = false;
        }
        if (!first) throw error;
        window.location.reload();
        return new Promise<never>(() => {});
      },
    ),
  );
}

const PrivateApplicationGate = lazyPage(() => import("./PrivateApp").then((module) => module.PrivateApplicationGate));
const AuthPage = lazyPage(() => import("../features/auth/AuthPage").then((module) => module.AuthPage));
const PilotGuidePage = lazyPage(() =>
  import("../features/help/PilotGuidePage").then((module) => module.PilotGuidePage),
);
const TrialGuidePage = lazyPage(() =>
  import("../features/help/TrialGuidePage").then((module) => module.TrialGuidePage),
);
const UserGuidePage = lazyPage(() => import("../features/help/UserGuidePage").then((module) => module.UserGuidePage));
const RequestDemoPage = lazyPage(() =>
  import("../features/auth/RequestDemoPage").then((module) => module.RequestDemoPage),
);

/** What shows while a screen's script loads: the application's "checking your session" card, which the session
 * check then shows itself, or an empty page for sign-in and the guides, as before any script ran (WEB-06). */
function Loading({ application = false }: { application?: boolean }) {
  if (!application) return <div aria-busy="true" />;
  return (
    <div className="auth-shell" aria-busy="true">
      <div className="auth-card">
        <span className="eyebrow">MDARIX secure application</span>
        <h1>Checking your session…</h1>
        <p>Customer application routes require an authenticated session.</p>
      </div>
    </div>
  );
}

const later = (page: ReactNode, application = false) => (
  <Suspense fallback={<Loading application={application} />}>{page}</Suspense>
);

export function App() {
  // Every page (the website, sign-in and the signed-in app) offers a reload once a newer MDARIX
  // is deployed than the one this tab loaded (features/shared/appVersion.ts).
  return (
    <>
      <Page />
      <NewVersionNotice />
    </>
  );
}

// Kept out of search results: sign-in and account screens, and the signed-in application.
const PRIVATE_PATHS = ["/signin", "/forgot-password", "/activate-account", "/reset-password", "/mfa", "/request-demo"];
const isPrivatePath = (path: string) =>
  PRIVATE_PATHS.includes(path) ||
  ["/app", "/platform-admin"].some((root) => path === root || path.startsWith(`${root}/`));

function Page() {
  const publicPath = window.location.pathname;
  // The free trial request is a page people search for; the screens behind it are not (site/seo.ts).
  useEffect(() => {
    if (publicPath === "/signup") applyPageMeta("/signup");
    // The application names its own tab (the organization); sign-in and account screens say what they are.
    else if (isPrivatePath(publicPath))
      applyPrivatePageMeta(
        PRIVATE_PATHS.includes(publicPath)
          ? publicPath === "/signin"
            ? "Sign in · MDARIX"
            : "MDARIX account"
          : undefined,
      );
  }, [publicPath]);
  if (publicPath === "/signup") return <SignupPage />;
  if (["/signin", "/forgot-password", "/activate-account", "/reset-password", "/mfa"].includes(publicPath))
    return later(<AuthPage mode={publicPath.slice(1)} />);
  if (publicPath === "/request-demo") return DEMO_REQUESTS_OFFERED ? later(<RequestDemoPage />) : <SignupPage />;
  if (publicPath === "/help/pilot-guide") return later(<PilotGuidePage />);
  if (publicPath === TRIAL_GUIDE_PATH) return later(<TrialGuidePage />);
  if (publicPath === USER_GUIDE_PATH) return later(<UserGuidePage />);
  // The signed-in application lives under /app and /platform-admin (router.ts). Match whole path segments, so a
  // website page such as /platform is never mistaken for /platform-admin.
  if (["/app", "/platform-admin"].some((root) => publicPath === root || publicPath.startsWith(`${root}/`)))
    return later(<PrivateApplicationGate />, true);
  // Everything else is the website: its pages, former page addresses it redirects, legal pages, and a "not found"
  // page for unknown addresses (rather than a sign-in prompt).
  return <PublicMegaSite path={publicPath} />;
}
