<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Stack, type Theme } from "../lib/api";
  import Button from "../lib/components/Button.svelte";

  export let projectId: string;

  // `null` is the id of the "Unassigned" bucket — a real drop target,
  // not a decoration: it is how a stack leaves a theme without joining
  // another one, and where stacks land when a theme is deleted.
  type Bucket = string | null;

  let themes: Theme[] = [];
  let stacksById: Record<string, Stack> = {};
  let themeStacks: Record<string, string[]> = {};
  let unassigned: string[] = [];
  let loading = true;
  let error = "";
  let newThemeName = "";

  // Tap-to-move (touch has no HTML5 drag-and-drop, so this path stays).
  let selectedStackId: string | null = null;
  // Pointer drag.
  let draggingStackId: string | null = null;
  let draggingFrom: Bucket = null;
  let hoveredBucket: Bucket | undefined = undefined;

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
      const claimed = new Set(Object.values(themeStacks).flat());
      unassigned = stacksData.map((s) => s.id).filter((id) => !claimed.has(id));
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function move(stackId: string, from: Bucket, to: Bucket) {
    if (from === to) return;
    selectedStackId = null;
    try {
      if (to === null) {
        if (from === null) return;
        await api.unassignStack(from, stackId);
      } else {
        await api.assignStack(to, stackId);
      }
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function bucketOf(stackId: string): Bucket {
    for (const theme of themes) {
      if ((themeStacks[theme.id] ?? []).includes(stackId)) return theme.id;
    }
    return null;
  }

  function moveSelected(to: Bucket) {
    if (!selectedStackId) return;
    move(selectedStackId, bucketOf(selectedStackId), to);
  }

  function onDragStart(event: DragEvent, stackId: string, from: Bucket) {
    draggingStackId = stackId;
    draggingFrom = from;
    selectedStackId = null;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      // Firefox refuses to start a drag without payload.
      event.dataTransfer.setData("text/plain", stackId);
    }
  }

  function onDragEnd() {
    draggingStackId = null;
    hoveredBucket = undefined;
  }

  function onDragOver(event: DragEvent, bucket: Bucket) {
    if (draggingStackId === null) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
    hoveredBucket = bucket;
  }

  function onDragLeave(bucket: Bucket) {
    if (hoveredBucket === bucket) hoveredBucket = undefined;
  }

  function onDrop(event: DragEvent, bucket: Bucket) {
    event.preventDefault();
    const stackId = draggingStackId;
    const from = draggingFrom;
    onDragEnd();
    if (stackId) move(stackId, from, bucket);
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

  async function remove(theme: Theme) {
    const count = (themeStacks[theme.id] ?? []).length;
    const tail = count
      ? ` Its ${count} stack${count === 1 ? "" : "s"} move back to Unassigned.`
      : "";
    if (!confirm(`Delete “${theme.name}”? Pages in it are deleted too.${tail}`)) return;
    try {
      await api.deleteTheme(theme.id);
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

  function photoCount(stackId: string): number {
    return stacksById[stackId]?.reference_ids.length ?? 0;
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
{:else}
  <p class="muted small hint-quiet">Drag a stack onto another theme, or tap it to move it.</p>
{/if}

{#if loading}
  <p class="muted">Loading themes…</p>
{:else}
  <div class="themes">
    {#each themes as theme (theme.id)}
      <article
        class="theme card"
        class:can-receive={selectedStackId !== null || draggingStackId !== null}
        class:hovered={hoveredBucket === theme.id}
        on:dragover={(e) => onDragOver(e, theme.id)}
        on:dragleave={() => onDragLeave(theme.id)}
        on:drop={(e) => onDrop(e, theme.id)}
      >
        <header>
          <h3>{theme.name}</h3>
          <button
            class="theme-action"
            on:click|stopPropagation={() => rename(theme)}
            aria-label={`Rename ${theme.name}`}>Rename</button>
          <button
            class="theme-action danger"
            on:click|stopPropagation={() => remove(theme)}
            aria-label={`Delete ${theme.name}`}>Delete</button>
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
              class:dragging={draggingStackId === stackId}
              draggable="true"
              on:dragstart={(e) => onDragStart(e, stackId, theme.id)}
              on:dragend={onDragEnd}
              on:click|stopPropagation={() =>
                (selectedStackId = selectedStackId === stackId ? null : stackId)}
              aria-pressed={selectedStackId === stackId}
              aria-label={`Stack with ${photoCount(stackId)} photos`}
            >
              {#if refId}
                <img src={api.thumbUrl(projectId, refId)} alt="" loading="lazy" />
              {/if}
              {#if photoCount(stackId) > 1}
                <span class="chip-count">{photoCount(stackId)}</span>
              {/if}
            </button>
          {/each}
          {#if (themeStacks[theme.id] ?? []).length === 0}
            <span class="muted small">No stacks in this theme.</span>
          {/if}
        </div>
      </article>
    {/each}

    <article
      class="theme card unassigned"
      class:can-receive={selectedStackId !== null || draggingStackId !== null}
      class:hovered={hoveredBucket === null && draggingStackId !== null}
      on:dragover={(e) => onDragOver(e, null)}
      on:dragleave={() => onDragLeave(null)}
      on:drop={(e) => onDrop(e, null)}
    >
      <header>
        <h3>Unassigned</h3>
      </header>
      {#if selectedStackId}
        <button class="move-here" on:click={() => moveSelected(null)}>
          Move selected stack out of its theme
        </button>
      {/if}
      <div class="stacks">
        {#each unassigned as stackId (stackId)}
          {@const refId = preview(stackId)}
          <button
            class="chip"
            class:selected={selectedStackId === stackId}
            class:dragging={draggingStackId === stackId}
            draggable="true"
            on:dragstart={(e) => onDragStart(e, stackId, null)}
            on:dragend={onDragEnd}
            on:click|stopPropagation={() =>
              (selectedStackId = selectedStackId === stackId ? null : stackId)}
            aria-pressed={selectedStackId === stackId}
            aria-label={`Unassigned stack with ${photoCount(stackId)} photos`}
          >
            {#if refId}
              <img src={api.thumbUrl(projectId, refId)} alt="" loading="lazy" />
            {/if}
            {#if photoCount(stackId) > 1}
              <span class="chip-count">{photoCount(stackId)}</span>
            {/if}
          </button>
        {/each}
        {#if unassigned.length === 0}
          <span class="muted small">Every stack belongs to a theme.</span>
        {/if}
      </div>
    </article>
  </div>

  {#if themes.length === 0}
    <p class="muted">
      No themes yet. Themes appear automatically after photos are organized. You can also add one
      above.
    </p>
  {/if}
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
  .hint-quiet { margin: 0 0 var(--space-3); }
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
  .theme.hovered {
    border-style: solid;
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }
  .unassigned { background: var(--color-border-soft); }
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
    gap: var(--space-2);
    margin-bottom: var(--space-3);
  }
  .theme h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    flex: 1;
  }
  .theme-action {
    appearance: none;
    background: transparent;
    border: 0;
    color: var(--color-text-muted);
    font-size: 0.85rem;
    padding: 4px 8px;
    border-radius: var(--radius-sm);
    cursor: pointer;
  }
  .theme-action:hover { color: var(--color-accent); background: var(--color-border-soft); }
  .theme-action.danger:hover { color: var(--color-danger); }
  .stacks {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
    min-height: 60px;
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
    cursor: grab;
    position: relative;
    transition: border-color 0.1s, transform 0.1s, opacity 0.1s;
  }
  .chip img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .chip:hover { transform: translateY(-1px); }
  .chip:active { cursor: grabbing; }
  .chip.selected { border-color: var(--color-accent); }
  .chip.dragging { opacity: 0.4; }
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
