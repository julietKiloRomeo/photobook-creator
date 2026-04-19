const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

let activeProjectId = null;

export function configureProject(projectId) {
  activeProjectId = projectId || null;
}

function apiPath(path) {
  if (activeProjectId) {
    return `/api/projects/${encodeURIComponent(activeProjectId)}${path}`;
  }
  return `/api${path}`;
}

async function request(path, options = {}) {
  const { method = 'GET', body } = options;

  try {
    const response = await fetch(apiPath(path), {
      method,
      headers: body ? JSON_HEADERS : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });

    let data = null;
    const contentType = response.headers.get('content-type') || '';

    if (contentType.includes('application/json')) {
      data = await response.json();
    }

    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      error,
      data: null,
    };
  }
}

export const api = {
  referenceImageUrl(referenceId) {
    return apiPath(`/references/${encodeURIComponent(referenceId)}/image`);
  },

  getReferences() {
    return request('/intake/references');
  },

  getStacks() {
    return request('/stacks');
  },

  splitStack(stackId, payload) {
    return request(`/stacks/${encodeURIComponent(stackId)}/split`, {
      method: 'POST',
      body: payload,
    });
  },

  pickDuel(payload) {
    return request('/duel/pick', {
      method: 'POST',
      body: payload,
    });
  },

  getThemes() {
    return request('/themes');
  },

  addTheme(payload) {
    return request('/themes', {
      method: 'POST',
      body: payload,
    });
  },

  patchTheme(themeId, payload) {
    return request(`/themes/${themeId}`, {
      method: 'PATCH',
      body: payload,
    });
  },

  deleteTheme(themeId) {
    return request(`/themes/${themeId}`, {
      method: 'DELETE',
    });
  },

  assignTheme(payload) {
    return request('/themes/assign', {
      method: 'POST',
      body: payload,
    });
  },

  getTimeline() {
    return request('/timeline');
  },

  getChapters() {
    return request('/chapters');
  },

  createChapter(payload) {
    return request('/chapters', {
      method: 'POST',
      body: payload,
    });
  },

  getChapterPages(chapterId) {
    return request(`/chapters/${chapterId}/pages`);
  },

  syncChapterPages(chapterId, payload) {
    return request(`/chapters/${chapterId}/pages`, {
      method: 'POST',
      body: payload,
    });
  },

  addPageText(pageId, payload) {
    return request(`/pages/${pageId}/items`, {
      method: 'POST',
      body: payload,
    });
  },

  uploadFiles(entries, options = {}) {
    const { onUploadProgress } = options;
    const form = new FormData();
    const files = [];
    let totalBytes = 0;
    (entries || []).forEach((entry) => {
      const file = entry?.file || entry;
      if (!file) {
        return;
      }

      const relativePath =
        entry?.relativePath ||
        file.webkitRelativePath ||
        file.name ||
        'file';

      form.append('files', file);
      form.append('relative_paths', relativePath);
      files.push(file);
      totalBytes += Number(file.size || 0);
    });

    const cumulativeBytes = [];
    {
      let running = 0;
      files.forEach((file) => {
        running += Number(file.size || 0);
        cumulativeBytes.push(running);
      });
    }

    const estimateUploadedFiles = (loadedBytes) => {
      if (!cumulativeBytes.length) {
        return 0;
      }
      let low = 0;
      let high = cumulativeBytes.length;
      while (low < high) {
        const mid = Math.floor((low + high) / 2);
        if (cumulativeBytes[mid] <= loadedBytes) {
          low = mid + 1;
        } else {
          high = mid;
        }
      }
      return low;
    };

    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', apiPath('/uploads'));

      xhr.upload.onprogress = (event) => {
        if (typeof onUploadProgress !== 'function') {
          return;
        }

        const loaded = Number(event.loaded || 0);
        const measuredTotal = Number(event.total || 0);
        const total = event.lengthComputable && measuredTotal > 0
          ? measuredTotal
          : totalBytes;

        const progress = total > 0
          ? Math.max(0, Math.min(1, loaded / total))
          : 0;

        onUploadProgress({
          loaded,
          total,
          progress,
          files_done: estimateUploadedFiles(loaded),
          files_total: files.length,
        });
      };

      xhr.onerror = () => {
        resolve({
          ok: false,
          status: 0,
          data: null,
        });
      };

      xhr.onload = () => {
        let data = null;
        try {
          data = typeof xhr.response === 'object' && xhr.response !== null
            ? xhr.response
            : JSON.parse(xhr.responseText || 'null');
        } catch (_error) {
          data = null;
        }

        resolve({
          ok: xhr.status >= 200 && xhr.status < 300,
          status: xhr.status,
          data,
        });
      };

      xhr.send(form);
    });
  },

  getUploads() {
    return request('/uploads');
  },

  getUploadProgress() {
    return request('/uploads/progress');
  },

  getOperation(operationId) {
    return request(`/operations/${encodeURIComponent(operationId)}`);
  },

  streamOperationEvents(operationId, handlers = {}) {
    const url = apiPath(`/operations/${encodeURIComponent(operationId)}/events`);
    if (typeof EventSource !== 'function') {
      if (typeof handlers.onError === 'function') {
        handlers.onError(new Error('EventSource is not supported in this browser'));
      }
      return () => {};
    }
    const source = new EventSource(url);
    const { onEvent, onDone, onError } = handlers;

    source.addEventListener('status', (event) => {
      try {
        const data = JSON.parse(event.data || '{}');
        if (typeof onEvent === 'function') {
          onEvent(data);
        }
      } catch (_error) {
        // Ignore malformed event payloads.
      }
    });

    source.addEventListener('done', (event) => {
      try {
        const data = JSON.parse(event.data || '{}');
        if (typeof onDone === 'function') {
          onDone(data);
        }
      } finally {
        source.close();
      }
    });

    source.onerror = (error) => {
      if (typeof onError === 'function') {
        onError(error);
      }
    };

    return () => source.close();
  },

  getDuplicates() {
    return request('/duplicates');
  },

  processProject() {
    return request('/process', {
      method: 'POST',
      body: {},
    });
  },

  resetProject() {
    return request('/reset', {
      method: 'POST',
      body: {},
    });
  },
};
