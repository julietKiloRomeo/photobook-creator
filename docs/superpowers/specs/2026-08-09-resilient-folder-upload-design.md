# Resilient Folder Upload Design

## Scope

This design resolves GitHub issues #18 through #21 as one coordinated upload-flow change:

- Decode HEIC and HEIF photos.
- Continue mixed batches when individual files are unsupported or corrupt.
- Support recursive folder selection.
- Show upload and processing progress.
- Start photo processing automatically after upload.
- Refresh stacks when processing finishes.
- Explain empty stack states accurately.

The design does not preserve source folder paths, infer themes from folders, add pause/resume, or persist an upload queue across navigation.

## User Flow

The project toolbar exposes two actions: **Add photos** and **Add folder**. Selecting either source starts upload immediately. Folder selection includes files from nested directories.

During transfer, the toolbar shows a determinate byte percentage and transferred/total size. After the server finishes ingesting the batch, the same status area switches to automatic photo-organizing progress. The explicit **Process new photos** action is removed.

When organizing completes, the stack screen reloads automatically. The final upload summary reports accepted photos and duplicates. If files were skipped, a disclosure lists each filename and a safe reason.

## Client Design

`ProjectToolbar` owns the combined upload and processing state:

1. Separate hidden file and folder inputs feed the same upload handler.
2. The folder input uses `multiple` and `webkitdirectory` so browsers recursively populate the `FileList`.
3. Both inputs explicitly accept standard image types plus `.heic` and `.heif`.
4. The folder path is not sent as application metadata. `File.webkitRelativePath` is only relevant to browser selection.
5. Obvious non-image folder entries are omitted before submission and included in the skipped summary as unsupported files.
6. One multipart request contains all candidate photos.
7. `XMLHttpRequest.upload.onprogress` reports bytes loaded and total bytes.
8. The returned job ID is polled with the existing job API.
9. Completion dispatches the existing events needed to reload project and stack data.

One request is intentional. It creates exactly one processing job, preserves the existing API shape, and avoids upload-session and finalization state. Chunking, retry queues, and resumable transfer remain out of scope.

## Server Design

The upload endpoint handles every file independently:

1. Validate that the project exists.
2. Attempt to ingest each submitted file.
3. Count valid new references as accepted.
4. Count existing hashes as duplicates.
5. Convert expected file-level failures into a rejection containing the original filename and a safe reason.
6. Continue with the remaining files after a rejection.
7. Enqueue exactly one `process` job when the batch accepts at least one new reference.
8. Return accepted, duplicate, and rejected results plus the processing job ID.

No processing job is created when the batch accepts zero new references. Unexpected infrastructure failures still fail the request rather than being mislabeled as bad input.

HEIC and HEIF decoding uses `pillow-heif`, registered once with Pillow before tier-1 decoding. Existing Pillow-supported formats continue through the same tier-1 path.

## Response Contract

The upload response extends the current result with:

- `accepted`: number of new references.
- `duplicates`: number of existing references encountered.
- `rejected`: ordered entries containing `filename` and `reason`.
- `job_id`: processing job identifier when at least one photo was accepted; otherwise `null`.

Rejection reasons are stable, user-safe categories such as `unsupported file type`, `file could not be decoded`, and `file is empty`. Internal exception text and filesystem paths are never returned.

## Error Behavior

Corrupt, empty, and unsupported files do not abort valid files in the same request. The final summary remains visible until the next upload begins.

Network failures and request-level server failures show one retryable batch error. A processing job starts only after server-side ingestion completes. This design does not provide partial-request retry because the client cannot reliably know which bytes reached the server; hash-based duplicate handling makes retrying the complete selection safe.

Processing failures replace progress with a clear error while preserving the upload summary. Successfully ingested originals remain available for a later retry.

## Empty States

The stack screen distinguishes these states:

- No project photos: prompt to add photos or a folder.
- Upload or processing active: explain that stacks will appear automatically.
- Pending filter empty with resolved stacks present: explain that organizing completed and link to **All**.
- Selected filter genuinely empty: state that no stacks match the filter.

No empty state tells the user to run processing manually.

## Responsive And Accessible Layout

The toolbar uses the existing flat surface and typography. On narrow viewports:

- **Add photos** and **Add folder** use a two-column action row when both labels fit.
- Progress label, percentage, bar, and detail occupy full-width rows.
- At narrower widths the actions may stack rather than overflow.
- Long filenames wrap with `overflow-wrap` and never create horizontal scrolling.
- The skipped-file disclosure is keyboard operable and exposes expanded state.
- Progress uses an accessible progress element or equivalent progressbar semantics with a textual status.
- Error and completion summaries use appropriate live-region semantics without repeatedly announcing every progress tick.

Automated browser coverage targets desktop Chromium and a 360-pixel mobile viewport.

## Testing

Backend tests cover:

- A real HEIC fixture ingests successfully.
- A mixed valid/corrupt/unsupported batch accepts valid files and returns ordered rejections.
- Duplicate counting remains correct when rejections are present.
- One accepted batch enqueues exactly one processing job.
- A zero-accepted batch enqueues no processing job.
- Rejection reasons do not expose internal exception details or paths.

Frontend component or browser tests cover:

- Recursive directory input submits nested supported photos.
- Unsupported folder entries appear in the skipped summary.
- Upload progress is visible and determinate.
- Upload completion transitions to processing status without a manual action.
- Processing completion refreshes stacks.
- Processing failure is visible and preserves the upload summary.
- Skipped-file disclosure works by keyboard.
- Desktop and 360-pixel layouts have no horizontal overflow, including long filenames.

The existing happy-path browser test is updated to wait for automatic processing instead of clicking **Process new photos**.

## Delivery Sequence

Issues #18 and #19 land together first because the response contract and automatic job creation define the client flow. Issues #20 and #21 then implement the progress and folder UI against that contract. Frontend validation follows the integrated branch so browser tests exercise the complete upload-to-stacks flow.
