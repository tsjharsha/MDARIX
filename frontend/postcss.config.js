import autoprefixer from "autoprefixer";

// Viewport lengths follow the page scale (styles.css, "Page scale"). With the page drawn at 80%, 100vh would fill
// only 80% of the window, so every vw/vh length (and its d/s/l variants) is divided by --page-zoom, which is 1
// unless the page is scaled. Media queries are left alone: they already measure the real window.
const VIEWPORT_LENGTH = /(?<![\w#.-])(-?(?:\d+\.?\d*|\.\d+))([dsl]?v[wh])\b/g;

export const viewportUnitsFollowPageZoom = {
  postcssPlugin: "viewport-units-follow-page-zoom",
  Declaration(decl) {
    if (decl.value.includes("--page-zoom")) return;
    decl.value = decl.value.replace(VIEWPORT_LENGTH, "calc($1$2 / var(--page-zoom, 1))");
  },
};

export default {
  plugins: [viewportUnitsFollowPageZoom, autoprefixer()],
};
