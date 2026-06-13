<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Project } from "../lib/api";

  export let projectId: string;
  export let tab: "stacks" | "themes" | "book";

  let project: Project | null = null;
  let error = "";

  async function load() {
    try {
      project = await api.getProject(projectId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  onMount(load);
  $: if (projectId) load();
</script>

<section class="placeholder">
  {#if error}
    <p class="error">{error}</p>
  {:else if !project}
    <p class="muted">Loading project…</p>
  {:else}
    <h2>{project.name}</h2>
    <p class="muted">
      The <strong>{tab}</strong> screen lands in sub-step 1.{tab === "stacks" ? 7 : tab === "themes" ? 8 : 9}.
    </p>
  {/if}
</section>

<style>
  .placeholder {
    padding: var(--space-6);
    background: var(--color-surface);
    border: 1px dashed var(--color-border);
    border-radius: var(--radius-lg);
    text-align: center;
  }
  h2 { margin: 0 0 var(--space-2); }
  .muted { color: var(--color-text-muted); margin: 0; }
  .error { color: var(--color-danger); }
</style>
