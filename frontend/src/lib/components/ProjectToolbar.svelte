<script lang="ts">
  import { createEventDispatcher, onDestroy } from "svelte";
  import { api, type Job, type UploadProgress, type UploadRejection } from "../api";
  import Button from "./Button.svelte";

  export let projectId: string;

  type Phase = "idle" | "uploading" | "processing";

  const dispatch = createEventDispatcher<{
    uploaded: void;
    processed: void;
    activity: { phase: Phase };
  }>();

  const ACCEPT = [
    "image/jpeg", ".jpeg", ".jpg",
    "image/png", ".png",
    "image/gif", ".gif",
    "image/webp", ".webp",
    "image/bmp", ".bmp",
    "image/tiff", ".tiff", ".tif",
    "image/heic", ".heic",
    "image/heif", ".heif",
  ].join(",");
  const SUPPORTED_EXTENSIONS = new Set([
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif", "heic", "heif",
  ]);

  let photoInput: HTMLInputElement;
  let folderInput: HTMLInputElement;
  let phase: Phase = "idle";
  let job: Job | null = null;
  let progress: UploadProgress | null = null;
  let uploadSummary: {
    accepted: number;
    duplicates: number;
    rejected: UploadRejection[];
    failedFiles: number;
  } | null = null;
  let error = "";
  let generation = 0;
  let activeProjectId = projectId;

  function setPhase(nextPhase: Phase) {
    phase = nextPhase;
    dispatch("activity", { phase });
  }

  function resetForProject(nextProjectId: string) {
    activeProjectId = nextProjectId;
    generation += 1;
    job = null;
    progress = null;
    uploadSummary = null;
    error = "";
    setPhase("idle");
  }

  const waitForPoll = () => new Promise((resolve) => setTimeout(resolve, 400));

  function directory(node: HTMLInputElement) {
    node.setAttribute("webkitdirectory", "");
    return { destroy: () => node.removeAttribute("webkitdirectory") };
  }

  function isSupported(file: File) {
    const extension = file.name.split(".").pop()?.toLowerCase();
    return extension !== undefined && SUPPORTED_EXTENSIONS.has(extension);
  }

  onDestroy(() => {
    generation += 1;
  });

  $: if (projectId !== activeProjectId) resetForProject(projectId);

  async function handleUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const selectedFiles = Array.from(input.files);
    const files = selectedFiles.filter(isSupported);
    const clientRejections: UploadRejection[] = selectedFiles
      .filter((file) => !isSupported(file))
      .map((file) => ({ filename: file.name, reason: "unsupported file type" }));
    const run = ++generation;
    input.value = "";
    error = "";
    job = null;
    progress = null;
    uploadSummary = null;
    if (files.length === 0) {
      uploadSummary = {
        accepted: 0,
        duplicates: 0,
        rejected: clientRejections,
        failedFiles: 0,
      };
      setPhase("idle");
      return;
    }
    setPhase("uploading");
    try {
      const result = await api.uploadFiles(projectId, files, (nextProgress) => {
        if (run === generation) progress = nextProgress;
      });
      if (run !== generation) return;
      // A chunk may have failed after earlier chunks landed: report the
      // partial outcome instead of discarding the successful prefix.
      error = result.failure?.message ?? "";
      const rejected = [...clientRejections, ...result.rejected];
      const landed = result.accepted + result.duplicates + rejected.length;
      if (landed === 0) {
        setPhase("idle");
        return;
      }
      uploadSummary = {
        accepted: result.accepted,
        duplicates: result.duplicates,
        rejected,
        failedFiles: result.failedFiles,
      };
      dispatch("uploaded");
      if (result.job_id === null) {
        setPhase("idle");
        return;
      }

      setPhase("processing");
      while (run === generation) {
        await waitForPoll();
        if (run !== generation) return;
        job = await api.getJob(result.job_id);
        if (run !== generation) return;
        if (job.status === "completed") {
          dispatch("processed");
          setPhase("idle");
          return;
        }
        if (job.status === "failed") {
          error = job.error || "Processing failed";
          setPhase("idle");
          return;
        }
      }
    } catch (e) {
      if (run !== generation) return;
      error = (e as Error).message;
      setPhase("idle");
    }
  }
</script>

<section class="toolbar" aria-label="Project actions">
  <input
    type="file"
    bind:this={photoInput}
    multiple
    accept={ACCEPT}
    on:change={handleUpload}
    style="display:none"
  />
  <input
    type="file"
    bind:this={folderInput}
    use:directory
    multiple
    accept={ACCEPT}
    on:change={handleUpload}
    style="display:none"
  />
  <div class="actions">
    <Button
      label="Add photos"
      on:click={() => photoInput.click()}
      disabled={phase !== "idle"}
    />
    <Button
      label="Add folder"
      variant="ghost"
      on:click={() => folderInput.click()}
      disabled={phase !== "idle"}
    />
  </div>
  {#if uploadSummary}
    <div class="upload-summary muted" aria-live="polite">
      <span>
        Added {uploadSummary.accepted}
        · {uploadSummary.duplicates} duplicate{uploadSummary.duplicates === 1 ? "" : "s"}
        {#if uploadSummary.failedFiles > 0}
          · {uploadSummary.failedFiles} file{uploadSummary.failedFiles === 1 ? "" : "s"} not uploaded
        {/if}
      </span>
      {#if uploadSummary.rejected.length > 0}
        <details>
          <summary>
            {uploadSummary.rejected.length} skipped {uploadSummary.rejected.length === 1 ? "file" : "files"}
          </summary>
          <ul>
            {#each uploadSummary.rejected as rejection}
              <li>
                <span class="filename">{rejection.filename}</span>
                <span>{rejection.reason}</span>
              </li>
            {/each}
          </ul>
        </details>
      {/if}
    </div>
  {/if}
  {#if phase === "uploading" && progress}
    <div class="progress-status">
      <progress
        aria-label="Upload progress"
        value={Math.round((progress.uploadedFiles / progress.totalFiles) * 100)}
        max="100"
      ></progress>
      <span class="muted">
        {#if progress.uploadedFiles >= progress.totalFiles}
          Finishing upload…
        {:else}
          {Math.floor(progress.uploadedFiles)} of {progress.totalFiles} files uploaded
        {/if}
      </span>
    </div>
  {:else if phase === "processing"}
    <div class="progress-status">
      <progress
        aria-label="Photo organizing progress"
        value={Math.round((job?.progress ?? 0) * 100)}
        max="100"
      ></progress>
      <span class="muted">
        {job?.message ?? "Organizing photos…"} · {Math.round((job?.progress ?? 0) * 100)}%
      </span>
    </div>
  {/if}
  {#if error}
    <span class="error" role="alert">{error}</span>
  {/if}
</section>

<style>
  .toolbar {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
  }
  .actions {
    display: grid;
    grid-template-columns: repeat(2, max-content);
    gap: var(--space-2);
    min-width: 0;
  }
  .upload-summary {
    display: grid;
    gap: var(--space-2);
    min-width: 0;
    overflow-wrap: anywhere;
  }
  details, summary, ul, li, .filename {
    min-width: 0;
    overflow-wrap: anywhere;
  }
  summary {
    width: fit-content;
    cursor: pointer;
  }
  ul {
    display: grid;
    gap: var(--space-2);
    margin: var(--space-2) 0 0;
    padding-left: var(--space-5);
  }
  li {
    display: grid;
    gap: 2px;
  }
  .filename {
    color: var(--color-text);
    font-weight: 500;
  }
  .progress-status {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  progress {
    width: 8rem;
    height: 0.5rem;
    accent-color: var(--color-accent);
  }
  .muted { color: var(--color-text-muted); font-size: 0.9rem; }
  .error {
    color: var(--color-danger);
    font-size: 0.9rem;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  @media (max-width: 36rem) {
    progress {
      flex: 1;
    }
  }
  @media (max-width: 320px) {
    .actions {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
