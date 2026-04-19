const createForm = document.getElementById('create-project-form');
const projectNameInput = document.getElementById('project-name');
const createButton = document.getElementById('create-project-btn');
const createStatus = document.getElementById('create-project-status');
const listStatus = document.getElementById('projects-load-status');
const refreshButton = document.getElementById('refresh-projects-btn');
const projectsList = document.getElementById('projects-list');

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle('error', isError);
}

function setCreateLoading(isLoading) {
  createButton.disabled = isLoading;
  projectNameInput.disabled = isLoading;
}

function setListLoading(isLoading) {
  refreshButton.disabled = isLoading;
}

function extractProjects(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  return [];
}

function formatCreatedAt(value) {
  if (!value) {
    return 'Created recently';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Created recently';
  }

  return `Created ${date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })}`;
}

function renderEmptyState(message) {
  projectsList.innerHTML = '';
  const item = document.createElement('li');
  item.className = 'empty-state';
  item.textContent = message;
  projectsList.append(item);
}

function createProjectItem(project) {
  const item = document.createElement('li');
  item.className = 'project-item';

  const main = document.createElement('div');
  main.className = 'project-main';

  const title = document.createElement('p');
  title.className = 'project-name';
  title.textContent = project.name || 'Untitled project';

  const meta = document.createElement('p');
  meta.className = 'project-meta';
  meta.textContent = formatCreatedAt(project.created_at);

  const openButton = document.createElement('button');
  openButton.type = 'button';
  openButton.className = 'open-btn';
  openButton.textContent = 'Open project';
  openButton.addEventListener('click', () => {
    if (!project.id) {
      return;
    }

    window.location.assign(`/darkroom/${encodeURIComponent(project.id)}`);
  });

  main.append(title, meta);
  item.append(main, openButton);

  return item;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;

  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : null;
    throw new Error(detail || `Request failed (${response.status})`);
  }

  return payload;
}

async function loadProjects() {
  setListLoading(true);
  setStatus(listStatus, 'Loading projects...');

  try {
    const payload = await fetchJson('/api/projects');
    const projects = extractProjects(payload);

    if (projects.length === 0) {
      renderEmptyState('No projects yet. Create your first photo book project.');
      setStatus(listStatus, '');
      return;
    }

    projectsList.innerHTML = '';
    projects
      .filter((project) => project && typeof project === 'object')
      .forEach((project) => {
        projectsList.append(createProjectItem(project));
      });

    setStatus(listStatus, `${projects.length} project${projects.length === 1 ? '' : 's'} loaded.`);
  } catch (error) {
    renderEmptyState('Could not load projects. Try again.');
    setStatus(listStatus, error instanceof Error ? error.message : 'Could not load projects.', true);
  } finally {
    setListLoading(false);
  }
}

async function createProject(name) {
  await fetchJson('/api/projects', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name }),
  });
}

createForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const name = projectNameInput.value.trim();
  if (!name) {
    setStatus(createStatus, 'Project name is required.', true);
    projectNameInput.focus();
    return;
  }

  setCreateLoading(true);
  setStatus(createStatus, 'Creating project...');

  try {
    await createProject(name);
    createForm.reset();
    setStatus(createStatus, 'Project created.');
    await loadProjects();
  } catch (error) {
    setStatus(createStatus, error instanceof Error ? error.message : 'Could not create project.', true);
  } finally {
    setCreateLoading(false);
  }
});

refreshButton.addEventListener('click', () => {
  void loadProjects();
});

void loadProjects();
