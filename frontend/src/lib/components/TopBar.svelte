<script lang="ts">
  import { navigate, type Route } from "../router";

  export let route: Route;
  export let projectName: string | null = null;

  $: tab = route.name === "project" ? route.tab : "stacks";
  $: projectId = route.name === "project" ? route.projectId : null;

  function go(target: "stacks" | "themes" | "book") {
    if (projectId) navigate(`/p/${projectId}/${target}`);
  }
</script>

<header class="topbar">
  <a class="brand" href="#/" aria-label="shoebox home">
    shoebox
  </a>
  {#if projectId}
    <div class="middle">
      <span class="project-name" title={projectName ?? ""}>{projectName ?? "…"}</span>
      <nav class="tabs" aria-label="Project sections">
        <button
          class:active={tab === "stacks"}
          on:click={() => go("stacks")}
          aria-current={tab === "stacks" ? "page" : undefined}
        >Stacks</button>
        <button
          class:active={tab === "themes"}
          on:click={() => go("themes")}
          aria-current={tab === "themes" ? "page" : undefined}
        >Themes</button>
        <button
          class:active={tab === "book"}
          on:click={() => go("book")}
          aria-current={tab === "book" ? "page" : undefined}
        >Book</button>
      </nav>
    </div>
  {/if}
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-4);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }
  .brand {
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--color-text);
    text-decoration: none;
  }
  .brand:hover {
    color: var(--color-accent);
  }
  .middle {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex: 1;
    min-width: 0;
  }
  .project-name {
    color: var(--color-text-soft);
    font-size: 0.95rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 22ch;
  }
  .tabs {
    display: flex;
    gap: var(--space-1);
    margin-left: auto;
    background: var(--color-bg);
    border-radius: var(--radius-md);
    padding: 2px;
  }
  .tabs button {
    appearance: none;
    background: transparent;
    border: 0;
    color: var(--color-text-soft);
    padding: 6px 14px;
    border-radius: var(--radius-sm);
    font-weight: 500;
    font-size: 0.92rem;
  }
  .tabs button.active {
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-sm);
  }
  @media (max-width: 480px) {
    .project-name { max-width: 12ch; }
    .tabs button { padding: 6px 10px; font-size: 0.85rem; }
  }
</style>
