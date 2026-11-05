import { useEffect, useRef, useState } from "react";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import type { SessionContext } from "./workspaceContext";

/*
 * Light and dark (0.10.91, the hero design's two themes): each person chooses Light, Dark or System (the default:
 * the device's setting), kept in this browser. Only the new navigation's shell applies it, by setting data-theme on
 * <html> while it is on screen (tokens.css holds both sets), so the website and the classic navigation stay light.
 */

export type ThemeChoice = "light" | "dark" | "system";
export type Theme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";
const themeKey = (session: SessionContext | null | undefined) => `mdarix.theme.${session?.user_id ?? ""}`;

/** The person's choice in this browser; System when none is kept, or storage cannot be read. */
export function readTheme(session: SessionContext | null | undefined): ThemeChoice {
  try {
    const kept = window.localStorage.getItem(themeKey(session));
    return kept === "light" || kept === "dark" ? kept : "system";
  } catch {
    return "system";
  }
}

export function saveTheme(session: SessionContext | null | undefined, choice: ThemeChoice) {
  try {
    if (choice === "system") window.localStorage.removeItem(themeKey(session));
    else window.localStorage.setItem(themeKey(session), choice);
  } catch {
    // No storage in this browser: the choice holds until the page is reloaded.
  }
}

/** The theme shown: the choice, or the device's setting under System. */
export const effectiveTheme = (choice: ThemeChoice, systemDark: boolean): Theme =>
  choice === "system" ? (systemDark ? "dark" : "light") : choice;

const systemIsDark = () => {
  try {
    return window.matchMedia?.(DARK_QUERY).matches ?? false;
  } catch {
    return false;
  }
};

/** The person's theme, applied to <html> while `on` (the new navigation's shell is mounted), and removed after. */
export function useTheme(session: SessionContext | null | undefined, on: boolean) {
  const [choice, setChoice] = useState<ThemeChoice>(() => readTheme(session));
  const [systemDark, setSystemDark] = useState(systemIsDark);
  useEffect(() => {
    const query = window.matchMedia?.(DARK_QUERY);
    if (!query) return;
    const follow = () => setSystemDark(query.matches);
    query.addEventListener?.("change", follow);
    return () => query.removeEventListener?.("change", follow);
  }, []);
  const theme = effectiveTheme(choice, systemDark);
  useEffect(() => {
    if (!on) return;
    const root = document.documentElement;
    root.dataset.theme = theme;
    return () => {
      delete root.dataset.theme;
    };
  }, [on, theme]);
  const choose = (next: ThemeChoice) => {
    saveTheme(session, next);
    setChoice(next);
  };
  return { choice, theme, choose };
}

const CHOICES: ReadonlyArray<{ value: ThemeChoice; label: string; Icon: typeof Sun }> = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

/** The top bar's sun or moon: Light, Dark or System, the current one checked. */
export function ThemeMenu({
  choice,
  theme,
  onChoose,
  defaultOpen = false,
}: {
  choice: ThemeChoice;
  theme: Theme;
  onChoose: (choice: ThemeChoice) => void;
  /** Tests only: render the menu open. */
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node))
        setOpen(false);
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", close);
    };
  }, [open]);
  const Icon = theme === "dark" ? Moon : Sun;
  const current = CHOICES.find((item) => item.value === choice)?.label ?? "System";
  return (
    <div className="uw-theme" ref={root}>
      <button
        type="button"
        className="ac-secondary uw-theme-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Theme: ${current}${choice === "system" ? ` (${theme === "dark" ? "dark" : "light"} now)` : ""}`}
        title="Theme"
        onClick={() => setOpen((value) => !value)}
      >
        <Icon size={18} aria-hidden="true" />
      </button>
      {open && (
        <div className="uw-pop uw-theme-menu" role="menu" aria-label="Theme">
          {CHOICES.map(({ value, label, Icon: ItemIcon }) => (
            <button
              key={value}
              type="button"
              role="menuitemradio"
              aria-checked={choice === value}
              className="uw-pop-option"
              onClick={() => {
                setOpen(false);
                onChoose(value);
              }}
            >
              <ItemIcon size={16} aria-hidden="true" />
              <span>{label}</span>
              {choice === value && <Check size={15} aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
