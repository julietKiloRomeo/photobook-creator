<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Page, type PageItem, type Stack, type Theme } from "../lib/api";
  import Button from "../lib/components/Button.svelte";

  export let projectId: string;

  let themes: Theme[] = [];
  let selectedThemeId: string | null = null;
  let pages: Page[] = [];
  let itemsByPage: Record<string, PageItem[]> = {};
  let stacksById: Record<string, Stack> = {};
  let themeStackIds: string[] = [];
  let loading = true;
  let error = "";
  let busy = false;
  let editingPageId: string | null = null;
  let pickerSlot: number | null = null;

  async function refreshThemes() {
    themes = await api.listThemes(projectId);
    if (themes.length && !selectedThemeId) {
      selectedThemeId = themes[0].id;
    }
  }

  async function refreshTheme() {
    if (!selectedThemeId) {
      pages = [];
      itemsByPage = {};
      themeStackIds = [];
      return;
    }
    pages = await api.listPages(selectedThemeId);
    const itemArrays = await Promise.all(pages.map((p) => api.listPageItems(p.id)));
    itemsByPage = Object.fromEntries(pages.map((p, i) => [p.id, itemArrays[i]]));
    themeStackIds = await api.listThemeStacks(selectedThemeId);

    const stacks = await api.listStacks(projectId);
    stacksById = Object.fromEntries(stacks.map((s) => [s.id, s]));
  }

  async function refresh() {
    loading = true;
    error = "";
    try {
      await refreshThemes();
      await refreshTheme();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function autoBuild() {
    busy = true;
    error = "";
    try {
      await api.autoBuild(projectId);
      await refresh();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function addPage() {
    if (!selectedThemeId) return;
    busy = true;
    try {
      await api.createPage(selectedThemeId);
      await refreshTheme();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  async function addTextBlock(pageId: string) {
    const content = prompt("Text for this slot:");
    if (!content) return;
    const items = itemsByPage[pageId] ?? [];
    const nextSlot = items.length ? Math.max(...items.map((i) => i.slot_index)) + 1 : 0;
    try {
      await api.addPageItem(pageId, { kind: "text", slot_index: nextSlot, text_content: content });
      await refreshTheme();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function deleteItem(itemId: string) {
    try {
      await api.deletePageItem(itemId);
      await refreshTheme();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function openPicker(pageId: string, slot: number) {
    editingPageId = pageId;
    pickerSlot = slot;
  }

  async function assignFromPicker(refId: string) {
    if (!editingPageId || pickerSlot === null) return;
    const items = itemsByPage[editingPageId] ?? [];
    const existing = items.find((it) => it.slot_index === pickerSlot && it.kind === "photo");
    try {
      if (existing) {
        await api.updatePageItem(existing.id, { reference_id: refId });
      } else {
        await api.addPageItem(editingPageId, {
          kind: "photo",
          slot_index: pickerSlot,
          reference_id: refId,
        });
      }
      editingPageId = null;
      pickerSlot = null;
      await refreshTheme();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function themePhotos(): { stackId: string; refId: string }[] {
    return themeStackIds
      .map((sid) => {
        const stack = stacksById[sid];
        if (!stack) return null;
        const refId = stack.picked_reference_id ?? stack.reference_ids[0];
        return refId ? { stackId: sid, refId } : null;
      })
      .filter((x): x is { stackId: string; refId: string } => x !== null);
  }

  function itemAt(pageId: string, slot: number): PageItem | undefined {
    return (itemsByPage[pageId] ?? []).find((it) => it.slot_index === slot);
  }

  onMount(refresh);
  $: if (projectId) refresh();
  $: if (selectedThemeId) refreshTheme();
</script>

<section class="actions">
  <Button label={busy ? "Working…" : "Auto-build draft"} on:click={autoBuild} disabled={busy} variant="ghost" />
  <a class="export-link" href={api.exportUrl(projectId)} target="_blank" rel="noopener">
    Export JSON ↓
  </a>
</section>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if loading}
  <p class="muted">Loading book…</p>
{:else if themes.length === 0}
  <p class="muted">Make some themes first (Themes tab), then come back.</p>
{:else}
  <nav class="theme-picker" aria-label="Pick a theme">
    {#each themes as theme (theme.id)}
      <button
        class:active={selectedThemeId === theme.id}
        on:click={() => (selectedThemeId = theme.id)}
      >{theme.name}</button>
    {/each}
  </nav>

  {#if selectedThemeId}
    <header class="theme-head">
      <h2>{themes.find((t) => t.id === selectedThemeId)?.name}</h2>
      <Button label="+ Add page" on:click={addPage} disabled={busy} variant="ghost" />
    </header>

    {#if pages.length === 0}
      <p class="muted">No pages yet. Tap <em>Auto-build draft</em> or <em>+ Add page</em>.</p>
    {:else}
      <ol class="pages">
        {#each pages as page (page.id)}
          <li class="page">
            <header>
              <span class="page-label">Page {page.order_index + 1}</span>
              <button class="page-action" on:click={() => addTextBlock(page.id)}>+ Text</button>
            </header>
            <div class="slots">
              {#each Array(4) as _, slot}
                {@const item = itemAt(page.id, slot)}
                <button
                  class="slot"
                  class:filled={item?.kind === "photo"}
                  on:click={() => openPicker(page.id, slot)}
                  aria-label={item ? "Change photo" : "Add photo"}
                >
                  {#if item?.kind === "photo" && item.reference_id}
                    <img src={api.mediumUrl(projectId, item.reference_id)} alt="" />
                  {:else if item?.kind === "text"}
                    <span class="text-block">{item.text_content}</span>
                  {:else}
                    <span class="empty">+</span>
                  {/if}
                </button>
                {#if item}
                  <button
                    class="remove"
                    on:click|stopPropagation={() => deleteItem(item.id)}
                    aria-label="Remove item"
                  >✕</button>
                {/if}
              {/each}
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  {/if}
{/if}

{#if editingPageId !== null && pickerSlot !== null}
  <div class="picker-backdrop" on:click={() => { editingPageId = null; pickerSlot = null; }} role="presentation"></div>
  <div class="picker" role="dialog" aria-modal="true" aria-label="Choose a photo">
    <header>
      <h3>Choose a photo</h3>
      <button class="close" on:click={() => { editingPageId = null; pickerSlot = null; }} aria-label="Close">✕</button>
    </header>
    <div class="picker-grid">
      {#each themePhotos() as photo (photo.stackId)}
        <button class="picker-tile" on:click={() => assignFromPicker(photo.refId)}>
          <img src={api.thumbUrl(projectId, photo.refId)} alt="" loading="lazy" />
        </button>
      {/each}
      {#if themePhotos().length === 0}
        <p class="muted">No photos available in this theme.</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .actions {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    margin-bottom: var(--space-4);
  }
  .export-link {
    margin-left: auto;
    padding: 8px 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    color: var(--color-text);
    text-decoration: none;
    font-weight: 500;
    font-size: 0.92rem;
    background: var(--color-surface);
  }
  .export-link:hover { background: var(--color-border-soft); text-decoration: none; }
  .theme-picker {
    display: flex;
    gap: var(--space-2);
    overflow-x: auto;
    padding-bottom: var(--space-2);
    margin-bottom: var(--space-3);
  }
  .theme-picker button {
    appearance: none;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 999px;
    padding: 6px 14px;
    color: var(--color-text-soft);
    font-size: 0.92rem;
    white-space: nowrap;
    cursor: pointer;
  }
  .theme-picker button.active {
    background: var(--color-accent);
    color: #fff;
    border-color: var(--color-accent);
  }
  .theme-head {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .theme-head h2 { margin: 0; font-size: 1.3rem; flex: 1; }
  .pages {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: var(--space-4);
  }
  .page {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: var(--space-3);
  }
  .page header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: var(--space-2);
  }
  .page-label { font-size: 0.85rem; color: var(--color-text-muted); }
  .page-action {
    appearance: none;
    background: transparent;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    padding: 4px 10px;
    font-size: 0.85rem;
    color: var(--color-text-soft);
  }
  .page-action:hover { background: var(--color-border-soft); }
  .slots {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2);
    aspect-ratio: 1 / 1;
    position: relative;
  }
  .slot {
    appearance: none;
    background: var(--color-border-soft);
    border: 1px dashed var(--color-border);
    border-radius: var(--radius-sm);
    overflow: hidden;
    padding: 0;
    cursor: pointer;
    position: relative;
  }
  .slot:hover { border-color: var(--color-accent); }
  .slot.filled { border: 1px solid var(--color-border); }
  .slot img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .text-block {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: var(--space-3);
    font-size: 0.95rem;
    color: var(--color-text);
    text-align: center;
  }
  .empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--color-text-muted);
    font-size: 1.6rem;
  }
  .remove {
    position: absolute;
    top: 4px; right: 4px;
    background: rgba(28,27,31,0.7);
    color: #fff;
    border: 0;
    border-radius: 999px;
    width: 22px; height: 22px;
    font-size: 0.75rem;
    cursor: pointer;
    display: none;
  }
  .slot.filled + .remove,
  .slots > .slot:not(.empty-slot) ~ .remove { display: inline; }
  /* picker modal */
  .picker-backdrop {
    position: fixed; inset: 0;
    background: rgba(28,27,31,0.45);
    z-index: 20;
  }
  .picker {
    position: fixed;
    inset: 0;
    z-index: 21;
    background: var(--color-bg);
    display: flex;
    flex-direction: column;
  }
  .picker header {
    display: flex; align-items: center;
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
  }
  .picker h3 { margin: 0; flex: 1; font-size: 1rem; }
  .close {
    appearance: none;
    background: transparent;
    border: 0;
    font-size: 1.4rem;
    color: var(--color-text-soft);
    padding: 4px 8px;
  }
  .picker-grid {
    flex: 1;
    overflow: auto;
    padding: var(--space-4);
    display: grid;
    gap: var(--space-3);
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    align-content: start;
  }
  .picker-tile {
    appearance: none;
    background: var(--color-surface);
    border: 2px solid var(--color-border);
    border-radius: var(--radius-sm);
    padding: 0;
    overflow: hidden;
    cursor: pointer;
  }
  .picker-tile:hover { border-color: var(--color-accent); }
  .picker-tile img { width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; }
  .muted { color: var(--color-text-muted); }
  .error { color: var(--color-danger); }
  @media (min-width: 720px) {
    .pages { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
    .picker { inset: 5% 8%; border-radius: var(--radius-lg); box-shadow: var(--shadow-md); overflow: hidden; }
  }
</style>
