<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Project } from "../lib/api";
  import ProjectToolbar from "../lib/components/ProjectToolbar.svelte";
  import BookScreen from "./BookScreen.svelte";
  import StacksScreen from "./StacksScreen.svelte";
  import ThemesScreen from "./ThemesScreen.svelte";

  export let projectId: string;
  export let tab: "stacks" | "themes" | "book";

  let project: Project | null = null;
  let error = "";
  // Bump this to force child screens to refetch after upload/process.
  let dataVersion = 0;

  async function load() {
    error = "";
    try {
      project = await api.getProject(projectId);
    } catch (e) {
      error = (e as Error).message;
      project = null;
    }
  }

  function bump() {
    dataVersion += 1;
  }

  onMount(load);
  $: if (projectId) load();
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}

{#if project}
  <ProjectToolbar
    {projectId}
    on:uploaded={bump}
    on:processed={bump}
  />

  {#key dataVersion + tab}
    {#if tab === "stacks"}
      <StacksScreen {projectId} />
    {:else if tab === "themes"}
      <ThemesScreen {projectId} />
    {:else}
      <BookScreen {projectId} />
    {/if}
  {/key}
{:else if !error}
  <p class="muted">Loading project…</p>
{/if}

<style>
  .error { color: var(--color-danger); }
  .muted { color: var(--color-text-muted); }
</style>
