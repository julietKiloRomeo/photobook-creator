// Thin fetch wrapper for the shoebox API. No third-party HTTP lib —
// keep the bundle small and the network surface obvious.

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const ct = response.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.blob()) as unknown as T;
}

// ----- Types mirror the backend Pydantic schemas. -----

export type Project = {
  id: string;
  name: string;
  created_at: string;
  status: string;
  photo_count: number;
};

export type Reference = {
  id: string;
  project_id: string;
  file_hash: string;
  captured_at: string | null;
  width: number | null;
  height: number | null;
  uploaded_at: string;
};

export type UploadResult = {
  accepted: number;
  duplicates: number;
  references: Reference[];
  rejected: UploadRejection[];
  job_id: string | null;
};

export type UploadRejection = {
  filename: string;
  reason: "unsupported file type" | "file could not be decoded" | "file is empty";
};

export type UploadProgress = {
  loaded: number;
  total: number;
};

export type Stack = {
  id: string;
  project_id: string;
  status: "pending" | "resolved" | "ignored";
  picked_reference_id: string | null;
  reference_ids: string[];
};

export type Theme = {
  id: string;
  project_id: string;
  name: string;
  color: string;
  order_index: number;
  ai_proposed: boolean;
};

export type Page = {
  id: string;
  theme_id: string;
  order_index: number;
  layout_id: string;
};

export type PageItem = {
  id: string;
  page_id: string;
  kind: "photo" | "text";
  reference_id: string | null;
  text_content: string | null;
  slot_index: number;
  position_json: string;
};

export type Job = {
  id: string;
  project_id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string | null;
  error: string | null;
};

// ----- Endpoints. -----

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),

  // Projects
  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (name: string) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  deleteProject: (id: string) =>
    request<void>(`/api/projects/${id}`, { method: "DELETE" }),

  // Uploads
  uploadFiles: (
    projectId: string,
    files: File[],
    onProgress?: (progress: UploadProgress) => void,
  ) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    return new Promise<UploadResult>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/projects/${projectId}/uploads`);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable && event.total > 0) {
          onProgress?.({ loaded: event.loaded, total: event.total });
        }
      });
      xhr.addEventListener("load", () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new ApiError(xhr.status, xhr.responseText || xhr.statusText));
          return;
        }
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } catch (error) {
          reject(error);
        }
      });
      xhr.addEventListener("error", () => reject(new TypeError("Failed to fetch")));
      xhr.addEventListener("abort", () =>
        reject(new DOMException("The operation was aborted.", "AbortError")),
      );
      xhr.send(form);
    });
  },
  thumbUrl: (projectId: string, referenceId: string) =>
    `/api/projects/${projectId}/references/${referenceId}/thumb`,
  mediumUrl: (projectId: string, referenceId: string) =>
    `/api/projects/${projectId}/references/${referenceId}/medium`,

  // Processing
  process: (projectId: string) =>
    request<Job>(`/api/projects/${projectId}/process`, { method: "POST" }),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),

  // Stacks
  listStacks: (projectId: string, status?: Stack["status"]) => {
    const qs = status ? `?status=${status}` : "";
    return request<Stack[]>(`/api/projects/${projectId}/stacks${qs}`);
  },
  pickStack: (stackId: string, referenceId: string) =>
    request<Stack>(`/api/stacks/${stackId}`, {
      method: "PATCH",
      body: JSON.stringify({ picked_reference_id: referenceId }),
    }),
  ignoreStack: (stackId: string) =>
    request<Stack>(`/api/stacks/${stackId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "ignored" }),
    }),

  // Themes
  listThemes: (projectId: string) =>
    request<Theme[]>(`/api/projects/${projectId}/themes`),
  createTheme: (projectId: string, name: string) =>
    request<Theme>(`/api/projects/${projectId}/themes`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  renameTheme: (themeId: string, name: string) =>
    request<Theme>(`/api/themes/${themeId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  deleteTheme: (themeId: string) =>
    request<void>(`/api/themes/${themeId}`, { method: "DELETE" }),
  assignStack: (themeId: string, stackId: string) =>
    request<void>(`/api/themes/${themeId}/assign`, {
      method: "POST",
      body: JSON.stringify({ stack_id: stackId }),
    }),
  unassignStack: (themeId: string, stackId: string) =>
    request<void>(`/api/themes/${themeId}/stacks/${stackId}`, { method: "DELETE" }),
  listThemeStacks: (themeId: string) =>
    request<string[]>(`/api/themes/${themeId}/stacks`),

  // Pages + items
  listPages: (themeId: string) => request<Page[]>(`/api/themes/${themeId}/pages`),
  createPage: (themeId: string) =>
    request<Page>(`/api/themes/${themeId}/pages`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  deletePage: (pageId: string) =>
    request<void>(`/api/pages/${pageId}`, { method: "DELETE" }),
  listPageItems: (pageId: string) =>
    request<PageItem[]>(`/api/pages/${pageId}/items`),
  addPageItem: (pageId: string, item: {
    kind: "photo" | "text";
    slot_index: number;
    reference_id?: string;
    text_content?: string;
  }) =>
    request<PageItem>(`/api/pages/${pageId}/items`, {
      method: "POST",
      body: JSON.stringify(item),
    }),
  updatePageItem: (
    itemId: string,
    patch: Partial<{
      reference_id: string;
      text_content: string;
      slot_index: number;
      position_json: string;
    }>,
  ) =>
    request<PageItem>(`/api/page-items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deletePageItem: (itemId: string) =>
    request<void>(`/api/page-items/${itemId}`, { method: "DELETE" }),

  // Book
  autoBuild: (projectId: string) =>
    request<{ themes: number; pages: number; items: number }>(
      `/api/projects/${projectId}/book/auto-build`,
      { method: "POST" },
    ),
  exportUrl: (projectId: string) => `/api/projects/${projectId}/export`,
};
