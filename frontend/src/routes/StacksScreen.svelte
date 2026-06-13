<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import { api, type Stack } from "../lib/api";
  import Button from "../lib/components/Button.svelte";

  export let projectId: string;

  const dispatch = createEventDispatcher<{ changed: void }>();

  let stacks: Stack[] = [];
  let filter: "pending" | "resolved" | "ignored" | "all" = "pending";
  let loading = true;
  let error = "";
  let openStack: Stack | null = null;
  let saving = false;

  async function refresh() {
    loading = true;
    error = "";
    try {
      stacks = await api.listStacks(projectId, filter === "all" ? undefined : filter);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function pick(reference_id: string) {
    if (!openStack) return;
    saving = true;
    try {
      const updated = await api.pickStack(openStack.id, reference_id);
      openStack = updated;
      await refresh();
      dispatch("changed");
    } catch (e) {
      error = (e as Error).message;
    } finally {
      saving = false;
    }
  }

  async function ignore() {
    if (!openStack) return;
    saving = true;
    try {
      await api.ignoreStack(openStack.id);
      openStack = null;
      await refresh();
      dispatch("changed");
    } catch (e) {
      error = (e as Error).message;
    } finally {
      saving = false;
    }
  }

  function previewRefId(stack: Stack): string {
    return stack.picked_reference_id ?? stack.reference_ids[0];
  }

  function counts(stacks: Stack[]) {
    return {
      pending: stacks.filter((s) => s.status === "pending").length,
      resolved: stacks.filter((s) => s.status === "resolved").length,
      ignored: stacks.filter((s) => s.status === "ignored").length,
    };
  }

  const FILTER_OPTIONS: ("pending" | "resolved" | "ignored" | "all")[] = [
    "pending",
    "resolved",
    "ignored",
    "all",
  ];

  $: countByStatus = counts(stacks);

  onMount(refresh);
  $: if (projectId) refresh();
  $: if (filter) refresh();
</script>

<div class="filters" role="tablist" aria-label="Filter by status">
  {#each FILTER_OPTIONS as f}
    <button
      role="tab"
      aria-selected={filter === f}
      class:active={filter === f}
      on:click={() => (filter = f)}
    >
      {f[0].toUpperCase()}{f.slice(1)}
    </button>
  {/each}
</div>

{#if error}
  <p class="error" role="alert">{error}</p>
{/if}

{#if loading}
  <p class="muted">Loading stacks…</p>
{:else if stacks.length === 0}
  <p class="muted">
    No stacks yet. Upload photos and tap <em>Process new photos</em> to create them.
  </p>
{:else}
  <ul class="grid" aria-label="Stacks">
    {#each stacks as stack (stack.id)}
      <li>
        <button class="card" on:click={() => (openStack = stack)} aria-label={`Open stack with ${stack.reference_ids.length} photos`}>
          <div class="thumb">
            <img
              src={api.thumbUrl(projectId, previewRefId(stack))}
              alt=""
              loading="lazy"
            />
            {#if stack.reference_ids.length > 1}
              <span class="count">{stack.reference_ids.length}</span>
            {/if}
          </div>
          <div class="meta">
            <span class="status status-{stack.status}">{stack.status}</span>
          </div>
        </button>
      </li>
    {/each}
  </ul>
{/if}

{#if openStack}
  <div
    class="modal-backdrop"
    on:click={() => (openStack = null)}
    role="presentation"
  ></div>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="picker-title">
    <header>
      <h2 id="picker-title">Pick the best shot</h2>
      <button class="close" on:click={() => (openStack = null)} aria-label="Close picker">✕</button>
    </header>
    <div class="picker-grid">
      {#each openStack.reference_ids as refId (refId)}
        <button
          class="pick"
          class:picked={openStack.picked_reference_id === refId}
          on:click={() => pick(refId)}
          disabled={saving}
          aria-label={openStack.picked_reference_id === refId ? "Selected" : "Choose this shot"}
        >
          <img src={api.mediumUrl(projectId, refId)} alt="" />
          {#if openStack.picked_reference_id === refId}
            <span class="pick-badge">Picked</span>
          {/if}
        </button>
      {/each}
    </div>
    <footer>
      <Button label="Ignore stack" variant="ghost" on:click={ignore} disabled={saving} />
      <Button label="Done" on:click={() => (openStack = null)} disabled={saving} />
    </footer>
  </div>
{/if}

<style>
  .filters {
    display: flex;
    gap: var(--space-1);
    background: var(--color-surface);
    padding: 4px;
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
    border: 1px solid var(--color-border);
    width: fit-content;
  }
  .filters button {
    appearance: none;
    background: transparent;
    border: 0;
    padding: 6px 14px;
    border-radius: var(--radius-sm);
    color: var(--color-text-soft);
    font-weight: 500;
    font-size: 0.9rem;
  }
  .filters button.active {
    background: var(--color-bg);
    color: var(--color-text);
  }
  .grid {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: var(--space-3);
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
  .card {
    appearance: none;
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    border-radius: var(--radius-md);
    overflow: hidden;
    padding: 0;
    cursor: pointer;
    width: 100%;
    text-align: left;
    transition: transform 0.1s, box-shadow 0.15s;
  }
  .card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); }
  .thumb {
    position: relative;
    aspect-ratio: 4 / 3;
    background: var(--color-border-soft);
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .count {
    position: absolute;
    top: 6px;
    right: 6px;
    background: rgba(28, 27, 31, 0.72);
    color: #fff;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 2px 7px;
    border-radius: 999px;
  }
  .meta {
    padding: var(--space-2) var(--space-3);
    font-size: 0.78rem;
  }
  .status {
    text-transform: capitalize;
    color: var(--color-text-soft);
  }
  .status-resolved { color: var(--color-success); }
  .status-ignored { color: var(--color-text-muted); }
  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(28, 27, 31, 0.45);
    z-index: 20;
  }
  .modal {
    position: fixed;
    inset: 0;
    z-index: 21;
    background: var(--color-bg);
    display: flex;
    flex-direction: column;
  }
  .modal header {
    display: flex; align-items: center;
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface);
  }
  .modal h2 { margin: 0; font-size: 1.05rem; flex: 1; }
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
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    align-content: start;
  }
  .pick {
    appearance: none;
    border: 2px solid var(--color-border);
    background: var(--color-surface);
    border-radius: var(--radius-md);
    overflow: hidden;
    padding: 0;
    cursor: pointer;
    position: relative;
    transition: border-color 0.15s, transform 0.1s;
  }
  .pick img {
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
    display: block;
  }
  .pick.picked { border-color: var(--color-accent); }
  .pick-badge {
    position: absolute;
    top: 8px; left: 8px;
    background: var(--color-accent);
    color: #fff;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 999px;
  }
  .modal footer {
    display: flex; gap: var(--space-3); justify-content: flex-end;
    padding: var(--space-3) var(--space-4);
    border-top: 1px solid var(--color-border);
    background: var(--color-surface);
  }
  .muted { color: var(--color-text-muted); }
  .error { color: var(--color-danger); }
  @media (min-width: 700px) {
    .grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .modal {
      inset: 5% 8%;
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-md);
      overflow: hidden;
    }
  }
</style>
