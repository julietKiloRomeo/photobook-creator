<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Project } from "./lib/api";
  import TopBar from "./lib/components/TopBar.svelte";
  import { route } from "./lib/router";
  import ProjectScreen from "./routes/ProjectScreen.svelte";
  import ProjectsScreen from "./routes/ProjectsScreen.svelte";

  let projectName: string | null = null;
  let projectCache: Record<string, Project> = {};

  async function ensureProjectName(projectId: string) {
    if (projectCache[projectId]) {
      projectName = projectCache[projectId].name;
      return;
    }
    try {
      const project = await api.getProject(projectId);
      projectCache[projectId] = project;
      projectName = project.name;
    } catch {
      projectName = null;
    }
  }

  $: if ($route.name === "project") {
    ensureProjectName($route.projectId);
  } else {
    projectName = null;
  }

  onMount(() => {
    // Health check on boot. If the backend is down, the projects list
    // call will fail loudly enough; this is just for the dev banner.
    api.health().catch(() => {});
  });
</script>

<TopBar route={$route} {projectName} />

<main>
  {#if $route.name === "projects"}
    <ProjectsScreen />
  {:else if $route.name === "project"}
    <ProjectScreen projectId={$route.projectId} tab={$route.tab} />
  {:else}
    <section class="not-found">
      <h2>Not found</h2>
      <p><a href="#/">Back to projects</a></p>
    </section>
  {/if}
</main>

<style>
  main {
    max-width: 920px;
    margin: 0 auto;
    padding: var(--space-5) var(--space-4) var(--space-8);
  }
  .not-found {
    text-align: center;
    padding: var(--space-6);
    color: var(--color-text-soft);
  }
  @media (min-width: 700px) {
    main { padding: var(--space-6) var(--space-5) var(--space-8); }
  }
</style>
