<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Stack, type Theme } from "../lib/api";
  import Button from "../lib/components/Button.svelte";

  export let projectId: string;

  let themes: Theme[] = [];
  let stacksById: Record<string, Stack> = {};
  let themeStacks: Record<string, string[]> = {};
  let loading = true;
  let error = "";
  let selectedStackId: string | null = null;
  let newThemeName = "";

  async function refresh() {
    loading = true;
    error = "";
    try {
      const [themesData, stacksData] = await Promise.all([
        api.listThemes(projectId),
        api.listStacks(projectId),
      ]);
      themes = themesData;
      stacksById = Object.fromEntries(stacksData.map((s) => [s.id, s]));
      const assignments = await Promise.all(
        themes.map((t) => api.listThemeStacks(t.id).then((ids) => [t.id, ids] as const)),
      );
      themeStacks = Object.fromEntries(assignments);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function moveSelected(themeId: string) {
    if (!selectedStackId) return;
    const sid = selectedStackId;
    selectedStackId = null;
    try {
      await api.assignStack(themeId, sid);
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function createTheme(event: Event) {
    event.preventDefault();
    if (!newThemeName.trim()) return;
    try {
      await api.createTheme(projectId, newThemeName.trim());
      newThemeName = "";
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function rename(theme: Theme) {
    const next = prompt("Rename theme", theme.name);
    if (!next || next === theme.name) return;
    try {
      await api.renameTheme(theme.id, next.trim());
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function preview(stackId: string): string | null {
    const stack = stacksById[stackId];
    if (!stack) return null;
    return stack.picked_reference_id ?? stack.reference_ids[0] ?? null;
  }

  onMount(refresh);
  $: if (projectId) refresh();
</script>

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}

<section class="new-theme card">
  <form on:submit={createTheme}>
    <input
      type="text"
      placeholder="New theme name (e.g. Beach Day)"
      bind:value={newThemeName}
      maxlength={120}
    />
    <Button label="Add theme" type="submit" disabled={!newThemeName.trim()} />
  </form>
</section>

{#if selectedStackId}
  <div class="hint" role="status">
    Tap a theme below to move the selected stack.
    <button class="link" on:click={() => (selectedStackId = null)}>Cancel</button>
  </div>
{/if}

{#if loading}
  <p class="muted">Loading themes…</p>
{:else if themes.length === 0}
  <p class="muted">No themes yet. Themes appear automatically after photos are organized. You can also add one above.</p>
{:else}
  <div class="themes">
    {#each themes as theme (theme.id)}
      <article class="theme card" class:can-receive={selectedStackId !== null}>
        <header>
          <h3>{theme.name}</h3>
          <button class="rename" on:click|stopPropagation={() => rename(theme)} aria-label={`Rename ${theme.name}`}>
            Rename
          </button>
        </header>
        {#if selectedStackId}
          <button class="move-here" on:click={() => moveSelected(theme.id)}>
            Move selected stack here
          </button>
        {/if}
        <div class="stacks">
          {#each themeStacks[theme.id] ?? [] as stackId (stackId)}
            {@const refId = preview(stackId)}
            <button
              class="chip"
              class:selected={selectedStackId === stackId}
              on:click|stopPropagation={() => (selectedStackId = selectedStackId === stackId ? null : stackId)}
              aria-pressed={selectedStackId === stackId}
              aria-label={`Stack with ${stacksById[stackId]?.reference_ids.length ?? 0} photos`}
            >
              {#if refId}
                <img src={api.thumbUrl(projectId, refId)} alt="" loading="lazy" />
              {/if}
              {#if stacksById[stackId] && stacksById[stackId].reference_ids.length > 1}
                <span class="chip-count">{stacksById[stackId].reference_ids.length}</span>
              {/if}
            </button>
          {/each}
          {#if (themeStacks[theme.id] ?? []).length === 0}
            <span class="muted small">No stacks in this theme.</span>
          {/if}
        </div>
      </article>
    {/each}
  </div>
{/if}

<style>
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-4);
  }
  .new-theme { margin-bottom: var(--space-4); }
  .new-theme form {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .new-theme input {
    flex: 1 1 220px;
    padding: 10px 14px;
    font-size: 1rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text);
  }
  .new-theme input:focus { outline: none; border-color: var(--color-accent); }
  .hint {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    background: var(--color-accent-soft);
    color: var(--color-accent);
    padding: 10px var(--space-4);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-3);
    font-size: 0.92rem;
  }
  .link {
    appearance: none;
    background: transparent;
    border: 0;
    color: var(--color-accent);
    font-weight: 500;
    text-decoration: underline;
    cursor: pointer;
  }
  .themes {
    display: grid;
    gap: var(--space-4);
    grid-template-columns: 1fr;
  }
  .theme {
    cursor: default;
    transition: border-color 0.15s, background 0.15s;
  }
  .theme.can-receive {
    border-style: dashed;
    border-color: var(--color-accent);
  }
  .move-here {
    appearance: none;
    background: var(--color-accent-soft);
    color: var(--color-accent);
    border: 0;
    border-radius: var(--radius-sm);
    padding: 8px 12px;
    margin-bottom: var(--space-3);
    cursor: pointer;
    font-weight: 500;
    font-size: 0.9rem;
    width: 100%;
  }
  .move-here:hover { background: #dedaf9; }
  .theme header {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .theme h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    flex: 1;
  }
  .rename {
    appearance: none;
    background: transparent;
    border: 0;
    color: var(--color-text-muted);
    font-size: 0.85rem;
    padding: 4px 8px;
    border-radius: var(--radius-sm);
  }
  .rename:hover { color: var(--color-accent); background: var(--color-border-soft); }
  .stacks {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .chip {
    appearance: none;
    border: 2px solid var(--color-border);
    background: var(--color-surface);
    border-radius: var(--radius-sm);
    padding: 0;
    width: 80px;
    height: 60px;
    overflow: hidden;
    cursor: pointer;
    position: relative;
    transition: border-color 0.1s, transform 0.1s;
  }
  .chip img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .chip:hover { transform: translateY(-1px); }
  .chip.selected { border-color: var(--color-accent); }
  .chip-count {
    position: absolute;
    top: 2px; right: 2px;
    background: rgba(28,27,31,0.7);
    color: #fff;
    font-size: 0.7rem;
    padding: 1px 5px;
    border-radius: 999px;
  }
  .small { font-size: 0.85rem; }
  .muted { color: var(--color-text-muted); }
  .error { color: var(--color-danger); }
  @media (min-width: 720px) {
    .themes { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
  }
</style>
