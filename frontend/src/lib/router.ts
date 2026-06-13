// Minimal hash-based router. Routes are URL fragments so the app works
// when served as static files behind any host (no server rewrites).
//
// Patterns:
//   /                       projects list
//   /p/:id                  project, default tab = stacks
//   /p/:id/stacks
//   /p/:id/themes
//   /p/:id/book

import { writable } from "svelte/store";

export type Route =
  | { name: "projects" }
  | { name: "project"; projectId: string; tab: "stacks" | "themes" | "book" }
  | { name: "not-found"; path: string };

function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "") || "/";
  if (path === "/" || path === "") return { name: "projects" };
  const m = path.match(/^\/p\/([^/]+)(?:\/(stacks|themes|book))?\/?$/);
  if (m) {
    const tab = (m[2] as "stacks" | "themes" | "book") ?? "stacks";
    return { name: "project", projectId: m[1], tab };
  }
  return { name: "not-found", path };
}

export const route = writable<Route>(parseHash(window.location.hash));

window.addEventListener("hashchange", () => {
  route.set(parseHash(window.location.hash));
});

export function navigate(path: string): void {
  window.location.hash = path;
}
