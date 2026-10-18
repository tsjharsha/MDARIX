import type { ReactElement } from "react";
import "./scenes.css";
import { decisionScenes } from "./decision";
import { investigationScenes } from "./investigation";
import { pageScenes } from "./pages";
import { platformScenes } from "./platform";
import { solutionScenes } from "./solutions";

/** A scene draws one picture's idea; it receives the picture's alt text as its accessible name. */
export type SceneComponent = (props: { label: string }) => ReactElement;

// Every animated scene, by the name of the picture it replaces (frontend/public/site/<name>.webp).
export const SCENES: Record<string, SceneComponent> = {
  ...platformScenes,
  ...investigationScenes,
  ...decisionScenes,
  ...solutionScenes,
  ...pageScenes,
};

/** The scene for a picture's address, if one has been drawn. */
export function sceneFor(src: string): SceneComponent | undefined {
  const name = /\/site\/([a-z0-9-]+)\.webp$/.exec(src)?.[1];
  if (!name) return undefined;
  return SCENES[name];
}
