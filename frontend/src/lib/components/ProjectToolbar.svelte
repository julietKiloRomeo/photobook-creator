<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { api, type Job } from "../api";
  import Button from "./Button.svelte";

  export let projectId: string;

  const dispatch = createEventDispatcher<{ uploaded: void; processed: void }>();

  let uploadInput: HTMLInputElement;
  let uploading = false;
  let processing = false;
  let job: Job | null = null;
  let uploadSummary: { accepted: number; duplicates: number } | null = null;
  let error = "";

  async function handleUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    uploading = true;
    error = "";
    try {
      const result = await api.uploadFiles(projectId, Array.from(input.files));
      uploadSummary = { accepted: result.accepted, duplicates: result.duplicates };
      dispatch("uploaded");
    } catch (e) {
      error = (e as Error).message;
    } finally {
      uploading = false;
      input.value = "";
    }
  }

  async function handleProcess() {
    processing = true;
    error = "";
    job = null;
    try {
      job = await api.process(projectId);
      while (job && job.status !== "completed" && job.status !== "failed") {
        await new Promise((r) => setTimeout(r, 400));
        job = await api.getJob(job.id);
      }
      if (job?.status === "completed") {
        dispatch("processed");
      } else if (job?.status === "failed") {
        error = job.error || "Processing failed";
      }
    } catch (e) {
      error = (e as Error).message;
    } finally {
      processing = false;
    }
  }
</script>

<section class="toolbar" aria-label="Project actions">
  <input
    type="file"
    bind:this={uploadInput}
    multiple
    accept="image/*"
    on:change={handleUpload}
    style="display:none"
  />
  <Button
    label={uploading ? "Uploading…" : "Upload photos"}
    on:click={() => uploadInput.click()}
    disabled={uploading}
  />
  <Button
    label={processing ? `Processing… ${Math.round((job?.progress ?? 0) * 100)}%` : "Process new photos"}
    variant="ghost"
    on:click={handleProcess}
    disabled={processing}
  />
  {#if uploadSummary}
    <span class="muted">
      Added {uploadSummary.accepted}
      {#if uploadSummary.duplicates > 0}
        · {uploadSummary.duplicates} duplicate{uploadSummary.duplicates === 1 ? "" : "s"}
      {/if}
    </span>
  {/if}
  {#if processing && job?.message}
    <span class="muted">{job.message}</span>
  {/if}
  {#if error}
    <span class="error" role="alert">{error}</span>
  {/if}
</section>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
    padding: var(--space-3) var(--space-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
  }
  .muted { color: var(--color-text-muted); font-size: 0.9rem; }
  .error { color: var(--color-danger); font-size: 0.9rem; }
</style>
