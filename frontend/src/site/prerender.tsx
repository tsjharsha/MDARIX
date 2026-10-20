// The website's pages as static HTML, for crawlers and link previews that run no JavaScript (WEB-05). The build
// renders this module on the server side (`vite build --ssr`) and scripts/prerender.mjs writes one file per page
// into dist: dist/home.html for "/", dist/<page>/index.html for the others. The browser then mounts the app with
// createRoot, which replaces the pre-rendered markup with the same page (src/main.tsx).
import { renderToStaticMarkup } from "react-dom/server";
import { PublicMegaSite } from "../PublicMegaSite";
import { AuthPage } from "../features/auth/AuthPage";
import { INDEXED_PATHS, SITE_URL, pageHead, type IndexedPath, type PageHead } from "./seo";

export { INDEXED_PATHS, pageHead, type IndexedPath, type PageHead };

type Location = { pathname: string; search: string; hash: string; origin: string; href: string };

/** The page a crawler gets at ``path``, as the browser first draws it: the website frame and the page itself, or the
 * trial sign-up form for /signup. Data the page loads at runtime (the ready videos, the legal texts, the company
 * details in the footer) is not there yet; the page's static text is. */
export function renderPage(path: IndexedPath): string {
  // A few components read the address while they render (the website's section anchor, sign-up's query string),
  // as the tests do: a stand-in window with this page's address, for this render only.
  const scope = globalThis as unknown as { window?: { location: Location } };
  const previous = scope.window;
  const location: Location = { pathname: path, search: "", hash: "", origin: SITE_URL, href: `${SITE_URL}${path}` };
  scope.window = { location };
  try {
    return renderToStaticMarkup(path === "/signup" ? <AuthPage mode="signup" /> : <PublicMegaSite path={path} />);
  } finally {
    if (previous === undefined) delete scope.window;
    else scope.window = previous;
  }
}
