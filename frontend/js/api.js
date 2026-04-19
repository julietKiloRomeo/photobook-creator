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
  getReferences() {
    return request('/intake/references');
  },

  getStacks() {
    return request('/stacks');
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

  async uploadFiles(files) {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));

    const response = await fetch(apiPath('/uploads'), {
      method: 'POST',
      body: form,
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : null;
    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  },

  getUploads() {
    return request('/uploads');
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
