const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

async function request(path, options = {}) {
  const { method = 'GET', body } = options;

  try {
    const response = await fetch(path, {
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
    return request('/api/intake/references');
  },

  getStacks() {
    return request('/api/stacks');
  },

  pickDuel(payload) {
    return request('/api/duel/pick', {
      method: 'POST',
      body: payload,
    });
  },

  getThemes() {
    return request('/api/themes');
  },

  addTheme(payload) {
    return request('/api/themes', {
      method: 'POST',
      body: payload,
    });
  },

  getTimeline() {
    return request('/api/timeline');
  },

  getChapters() {
    return request('/api/chapters');
  },

  createChapter(payload) {
    return request('/api/chapters', {
      method: 'POST',
      body: payload,
    });
  },

  getChapterPages(chapterId) {
    return request(`/api/chapters/${chapterId}/pages`);
  },

  syncChapterPages(chapterId, payload) {
    return request(`/api/chapters/${chapterId}/pages`, {
      method: 'POST',
      body: payload,
    });
  },

  addPageText(pageId, payload) {
    return request(`/api/pages/${pageId}/items`, {
      method: 'POST',
      body: payload,
    });
  },
};
