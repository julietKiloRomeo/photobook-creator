<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Project } from "../lib/api";
  import Button from "../lib/components/Button.svelte";
  import { navigate } from "../lib/router";

  let projects: Project[] = [];
  let name = "";
  let creating = false;
  let loading = true;
  let error = "";

  async function refresh() {
    loading = true;
    error = "";
    try {
      projects = await api.listProjects();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function handleCreate(event: Event) {
    event.preventDefault();
    if (!name.trim() || creating) return;
    creating = true;
    error = "";
    try {
      const project = await api.createProject(name.trim());
      navigate(`/p/${project.id}`);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      creating = false;
    }
  }

  async function handleDelete(project: Project) {
    if (!confirm(`Delete "${project.name}"? Photos will be removed too.`)) return;
    try {
      await api.deleteProject(project.id);
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  onMount(refresh);
</script>

<section class="hero">
  <h1>Your shoeboxes</h1>
  <p class="tagline">
    Each shoebox is one photo book in the making. Create one, drop photos in,
    and the family takes it from there.
  </p>
</section>

<section class="card create" aria-labelledby="create-title">
  <h2 id="create-title">Start a new shoebox</h2>
  <form on:submit={handleCreate}>
    <label for="project-name" class="sr-only">Name</label>
    <input
      id="project-name"
      type="text"
      placeholder="Italy 2026"
      bind:value={name}
      maxlength={120}
      required
      autocomplete="off"
    />
    <Button label={creating ? "Creating…" : "Create"} type="submit" disabled={creating || !name.trim()} />
  </form>
</section>

<section class="card list" aria-labelledby="list-title">
  <header class="list-head">
    <h2 id="list-title">All shoeboxes</h2>
    <button class="refresh" on:click={refresh} aria-label="Refresh list" type="button">⟳</button>
  </header>

  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if projects.length === 0}
    <p class="muted">No shoeboxes yet. Create one above.</p>
  {:else}
    <ul>
      {#each projects as project (project.id)}
        <li>
          <a href={`#/p/${project.id}`} class="project-link">
            <span class="project-link-name">{project.name}</span>
            <span class="project-link-meta">
              {new Date(project.created_at).toLocaleDateString()}
            </span>
          </a>
          <button class="del" on:click={() => handleDelete(project)} aria-label={`Delete ${project.name}`} type="button">
            Delete
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .hero {
    margin-bottom: var(--space-6);
  }
  h1 {
    margin: 0;
    font-size: 2.25rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .tagline {
    margin: var(--space-2) 0 0;
    color: var(--color-text-soft);
    max-width: 56ch;
  }
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: var(--space-5);
    margin-bottom: var(--space-4);
  }
  .card h2 {
    margin: 0 0 var(--space-3);
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--color-text-soft);
  }
  .create form {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .create input {
    flex: 1 1 220px;
    padding: 10px 14px;
    font-size: 1rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text);
  }
  .create input:focus {
    outline: none;
    border-color: var(--color-accent);
  }
  .list-head {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-3);
  }
  .list-head h2 { margin: 0; flex: 1; }
  .refresh {
    appearance: none;
    background: transparent;
    border: 1px solid var(--color-border);
    color: var(--color-text-soft);
    padding: 4px 10px;
    border-radius: var(--radius-sm);
    font-size: 1.1rem;
  }
  .refresh:hover { background: var(--color-border-soft); }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) 0;
    border-top: 1px solid var(--color-border-soft);
  }
  li:first-child { border-top: 0; }
  .project-link {
    flex: 1;
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    color: var(--color-text);
    text-decoration: none;
  }
  .project-link:hover .project-link-name { color: var(--color-accent); }
  .project-link-name {
    font-size: 1.05rem;
    font-weight: 500;
  }
  .project-link-meta {
    color: var(--color-text-muted);
    font-size: 0.85rem;
  }
  .del {
    appearance: none;
    background: transparent;
    border: 1px solid var(--color-border);
    color: var(--color-text-soft);
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    font-size: 0.85rem;
  }
  .del:hover { color: var(--color-danger); }
  .muted {
    color: var(--color-text-muted);
    margin: 0;
  }
  .error {
    margin: 0 0 var(--space-3);
    color: var(--color-danger);
  }
  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
  }
</style>
