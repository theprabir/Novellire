import { api } from './api.js';
import {
  count,
  el,
  icon,
  initials,
  toast,
} from './ui.js';
import { renderProjects } from './views/projects.js';
import { renderWorkspace } from './views/workspace.js';
import { renderPreview } from './views/preview.js';
import { renderSettings } from './views/settings.js';
import { renderChat, renderScope } from './views/scopes.js';

const NAV = [
  { key: 'workspace', label: 'Workspace', icon: 'layers' },
  { key: 'preview', label: 'Preview', icon: 'book' },
  { key: 'chat', label: 'Chat', icon: 'message', pill: 'Phase 4' },
  { key: 'memory', label: 'Memory', icon: 'database', pill: 'Phase 3' },
  { key: 'continuity', label: 'Continuity', icon: 'shield', pill: 'Phase 5' },
  { key: 'export', label: 'Export', icon: 'download', pill: 'Phase 6' },
  { key: 'settings', label: 'Settings', icon: 'sliders' },
];

const UI_FONTS = {
  system: '"Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, sans-serif',
  humanist: '"Segoe UI", "Trebuchet MS", Verdana, sans-serif',
  serif: 'Georgia, "Iowan Old Style", "Times New Roman", serif',
  mono: '"Cascadia Code", "JetBrains Mono", Consolas, monospace',
};

const READING_FONTS = {
  garamond: '"EB Garamond", "Adobe Garamond Pro", Garamond, "Times New Roman", Georgia, serif',
  georgia: 'Georgia, "Iowan Old Style", "Times New Roman", serif',
  palatino: '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif',
};

export const state = {
  meta: null,
  projects: [],
  activeProjectId: null,
  tree: null,
  manuscript: null,
  details: { bible: [], characters: [] },
  settings: null,
  ollama: null,
  route: { name: 'projects', a: null, b: null },
  workspaceType: 'chapters',
  selectedId: null,
  selectedSceneId: null,
  previewChapterId: null,
  filesOpen: { bible: true, characters: true, chapters: true },
  loading: true,
};

let context = null;
let mediaQuery = null;

/* -------------------------------------------------------------------------
   Boot
   ------------------------------------------------------------------------- */

async function boot() {
  bindChrome();
  try {
    const [meta, projectsPayload, settings, ollama] = await Promise.all([
      api.get('/api/meta'),
      api.get('/api/projects'),
      api.get('/api/settings'),
      api.get('/api/ollama/status'),
    ]);
    state.meta = meta;
    state.projects = projectsPayload.projects;
    state.activeProjectId = projectsPayload.active_project_id;
    state.settings = settings;
    state.ollama = ollama;
    applyAppearance(settings.appearance);
    await loadProjectData();
    state.route = parseHash();
    applyRouteDefaults();
    state.loading = false;
    render();
  } catch (error) {
    state.loading = false;
    renderFatal(error);
  }
}

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const parts = raw.split('/').filter(Boolean).map(decodeURIComponent);
  return { name: parts[0] || 'projects', a: parts[1] || null, b: parts[2] || null };
}

function applyRouteDefaults() {
  const { route } = state;
  if (route.name === 'workspace') {
    if (route.a) state.workspaceType = route.a;
    if (route.b) state.selectedId = Number(route.b);
  }
  if (route.name === 'preview' && route.a) state.previewChapterId = Number(route.a);
}

async function loadProjectData() {
  if (!state.activeProjectId) {
    state.tree = null;
    state.manuscript = null;
    state.details = { bible: [], characters: [] };
    return;
  }
  try {
    const [tree, manuscript, bible, characters] = await Promise.all([
      api.get(`/api/projects/${state.activeProjectId}/tree`),
      api.get(`/api/projects/${state.activeProjectId}/manuscript`),
      api.get(`/api/projects/${state.activeProjectId}/bible`),
      api.get(`/api/projects/${state.activeProjectId}/characters`),
    ]);
    state.tree = tree;
    state.manuscript = manuscript;
    state.details = { bible, characters };
  } catch (error) {
    if (error.status === 404) {
      state.activeProjectId = null;
      state.tree = null;
      state.manuscript = null;
      state.details = { bible: [], characters: [] };
      await refreshProjects();
    } else {
      toast(error.message, 'error');
    }
  }
}

async function refreshProjects() {
  const payload = await api.get('/api/projects');
  state.projects = payload.projects;
  state.activeProjectId = payload.active_project_id;
}

async function refreshOllama() {
  state.ollama = await api.get('/api/ollama/status');
  renderShell();
}

async function reloadAll() {
  try {
    await Promise.all([refreshProjects(), refreshOllama()]);
    await loadProjectData();
    render();
    toast('Project data reloaded.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function selectProject(projectId) {
  try {
    await api.post(`/api/projects/${projectId}/activate`, {});
    state.activeProjectId = projectId;
    state.selectedId = null;
    state.selectedSceneId = null;
    state.previewChapterId = null;
    await Promise.all([refreshProjects(), loadProjectData()]);
    if (window.location.hash !== '#/workspace') window.location.hash = '#/workspace';
    render();
  } catch (error) {
    toast(error.message, 'error');
  }
}

/* -------------------------------------------------------------------------
   Appearance
   ------------------------------------------------------------------------- */

function resolveTheme(theme) {
  if (theme !== 'system') return theme;
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function applyAppearance(appearance) {
  const root = document.documentElement;
  root.dataset.theme = resolveTheme(appearance.theme);
  root.dataset.accent = appearance.accent;
  root.dataset.readingWidth = appearance.reading_width;
  root.style.setProperty('--ui-font', UI_FONTS[appearance.ui_font] || UI_FONTS.system);
  root.style.setProperty(
    '--reading-font',
    READING_FONTS[appearance.reading_font] || READING_FONTS.garamond
  );
  root.style.setProperty('--ui-font-size', `${appearance.ui_font_size}px`);
  root.style.setProperty('--reading-font-size', `${appearance.reading_font_size}px`);
  try {
    localStorage.setItem('novellire.appearance', JSON.stringify(appearance));
  } catch (error) { /* storage is optional */ }
}

async function saveAppearance(patch, { rerender = true } = {}) {
  const next = { ...state.settings.appearance, ...patch };
  state.settings.appearance = next;
  applyAppearance(next);
  try {
    const saved = await api.put('/api/settings/appearance', next);
    state.settings.appearance = saved;
    applyAppearance(saved);
  } catch (error) {
    toast(error.message, 'error');
    return null;
  }
  if (rerender) render();
  else renderShell();
  return state.settings.appearance;
}

async function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  await saveAppearance({ theme: next });
}

/* -------------------------------------------------------------------------
   Rendering
   ------------------------------------------------------------------------- */

function makeContext() {
  return {
    state,
    refresh: async () => {
      await loadProjectData();
      render();
    },
    reloadProjects: async () => {
      await refreshProjects();
      render();
    },
    refreshOllama,
    selectProject,
    saveAppearance,
    render,
    renderShell,
    navigate: (hash) => { window.location.hash = hash; },
  };
}

function render() {
  const view = document.getElementById('view');
  if (!view) return;
  if (!context) context = makeContext();
  view.replaceChildren();
  let node;
  switch (state.route.name) {
    case 'workspace':
      node = renderWorkspace(context);
      break;
    case 'preview':
      node = renderPreview(context);
      break;
    case 'settings':
      node = renderSettings(context);
      break;
    case 'chat':
      node = renderChat(context);
      break;
    case 'memory':
    case 'continuity':
    case 'export':
      node = renderScope(context, state.route.name);
      break;
    case 'projects':
    default:
      node = renderProjects(context);
      break;
  }
  view.append(node);
  renderShell();
  document.documentElement.dataset.mobileNav = 'closed';
  updateScrim();
  view.scrollTop = 0;
}

function renderShell() {
  renderProjectList();
  renderNav();
  renderFileTree();
  renderFooter();
  renderTopbar();
}

function renderProjectList() {
  const host = document.getElementById('project-list');
  if (!host) return;
  host.replaceChildren();
  if (!state.projects.length) {
    host.append(el('div', { class: 'tree-empty' }, 'No projects yet'));
    return;
  }
  for (const project of state.projects) {
    host.append(
      el(
        'button',
        {
          class: 'project-chip',
          type: 'button',
          title: `${project.name} — ${count(project.words_generated)} words`,
          'aria-current': project.id === state.activeProjectId ? 'true' : undefined,
          onClick: () => selectProject(project.id),
        },
        el('span', { class: 'dot' }, initials(project.name)),
        el('span', { class: 'label' }, project.name),
        el('span', { class: 'count' }, count(project.generations))
      )
    );
  }
}

function renderNav() {
  const host = document.getElementById('side-nav');
  if (!host) return;
  host.replaceChildren();
  for (const item of NAV) {
    host.append(
      el(
        'a',
        {
          class: 'nav-item',
          href: `#/${item.key}`,
          'aria-current': state.route.name === item.key ? 'page' : undefined,
        },
        icon(item.icon),
        el('span', { class: 'label' }, item.label),
        item.pill ? el('span', { class: 'pill' }, item.pill) : null
      )
    );
  }
}

function categoryLabel(key) {
  return (state.meta?.bible_categories || []).find((item) => item.key === key)?.label || key;
}

function treeGroup(label, type, items, iconName) {
  const open = state.filesOpen[type];
  const group = el('div', { class: 'tree-group' });
  group.append(
    el(
      'button',
      {
        class: 'tree-toggle',
        type: 'button',
        'aria-expanded': open ? 'true' : 'false',
        onClick: () => {
          state.filesOpen[type] = !state.filesOpen[type];
          renderFileTree();
        },
      },
      icon('chevron-right', 'icon'),
      el('span', {}, `${label} · ${items.length}`)
    )
  );
  if (!open) return group;
  if (!items.length) {
    group.append(el('div', { class: 'tree-empty' }, `No ${label.toLowerCase()} yet`));
    return group;
  }
  for (const item of items) {
    group.append(
      el(
        'a',
        {
          class: 'tree-item',
          href: `#/workspace/${type}/${item.id}`,
          'aria-current':
            state.route.name === 'workspace' &&
            state.workspaceType === type &&
            Number(state.selectedId) === item.id
              ? 'true'
              : undefined,
        },
        icon(iconName, 'icon sm'),
        el('span', { class: 'label' }, item.title),
        item.meta ? el('span', { class: 'meta' }, item.meta) : null
      )
    );
  }
  return group;
}

function renderFileTree() {
  const host = document.getElementById('file-tree');
  if (!host) return;
  host.replaceChildren();
  if (!state.tree) {
    host.append(el('div', { class: 'tree-empty' }, 'Select a project'));
    return;
  }
  host.append(
    treeGroup(
      'Story bible',
      'bible',
      state.tree.bible.map((entry) => ({
        id: entry.id,
        title: entry.title,
        meta: categoryLabel(entry.category),
      })),
      'file'
    )
  );
  host.append(
    treeGroup(
      'Characters',
      'characters',
      state.tree.characters.map((character) => ({ id: character.id, title: character.name })),
      'user'
    )
  );
  host.append(
    treeGroup(
      'Chapters',
      'chapters',
      state.tree.chapters.map((chapter) => ({
        id: chapter.id,
        title: `${chapter.position}. ${chapter.title}`,
        meta: `${chapter.scenes.length}`,
      })),
      'file'
    )
  );
}

function renderFooter() {
  const host = document.getElementById('sidebar-foot');
  if (!host) return;
  host.replaceChildren();
  const available = Boolean(state.ollama?.available);
  const model = state.settings?.generation?.model || 'Choose a model';
  host.append(
    el('span', {
      class: `status-dot ${available ? 'online' : 'offline'}`,
      title: available ? 'Ollama connected' : 'Ollama offline',
    }),
    el('span', { class: 'model-name' }, available ? model : 'Ollama offline'),
    el('a', { class: 'icon-btn', href: '#/settings', title: 'Settings', 'aria-label': 'Settings' }, icon('settings'))
  );
}

function renderTopbar() {
  const crumbs = document.getElementById('crumbs');
  const actions = document.getElementById('topbar-actions');
  if (!crumbs || !actions) return;
  crumbs.replaceChildren();
  const project = state.projects.find((item) => item.id === state.activeProjectId);
  crumbs.append(el('a', { class: 'crumb', href: '#/projects' }, 'Projects'));
  if (project) {
    crumbs.append(icon('chevron-right'), el('span', { class: 'crumb' }, project.name));
  }
  const label = NAV.find((item) => item.key === state.route.name)?.label || 'Projects';
  crumbs.append(icon('chevron-right'), el('span', { class: 'crumb current' }, label));

  actions.replaceChildren();
  actions.append(
    el(
      'button',
      {
        class: 'icon-btn',
        type: 'button',
        title: 'Toggle light and dark theme',
        'aria-label': 'Toggle light and dark theme',
        onClick: toggleTheme,
      },
      icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon')
    ),
    el(
      'button',
      {
        class: 'icon-btn',
        type: 'button',
        title: 'Reload project data',
        'aria-label': 'Reload project data',
        onClick: reloadAll,
      },
      icon('refresh')
    )
  );
}

function renderFatal(error) {
  const view = document.getElementById('view');
  if (!view) return;
  view.replaceChildren(
    el(
      'div',
      { class: 'view-inner' },
      el(
        'div',
        { class: 'empty' },
        icon('alert', 'icon'),
        el('h3', {}, 'Novellire could not start'),
        el('p', {}, error?.message || 'The server did not answer.'),
        el(
          'button',
          { class: 'btn btn-primary', type: 'button', onClick: () => window.location.reload() },
          'Retry'
        )
      )
    )
  );
}

/* -------------------------------------------------------------------------
   Chrome events
   ------------------------------------------------------------------------- */

function updateScrim() {
  const scrim = document.getElementById('scrim');
  const open = document.documentElement.dataset.mobileNav === 'open';
  if (scrim) scrim.hidden = !open;
}

function bindChrome() {
  const collapse = document.getElementById('sidebar-collapse');
  collapse?.addEventListener('click', () => {
    const root = document.documentElement;
    root.dataset.sidebar = root.dataset.sidebar === 'collapsed' ? 'expanded' : 'collapsed';
    try {
      localStorage.setItem('novellire.sidebar', root.dataset.sidebar);
    } catch (error) { /* storage is optional */ }
  });

  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    document.documentElement.dataset.mobileNav = 'open';
    updateScrim();
  });

  document.getElementById('scrim')?.addEventListener('click', () => {
    document.documentElement.dataset.mobileNav = 'closed';
    updateScrim();
  });

  window.addEventListener('hashchange', async () => {
    state.route = parseHash();
    applyRouteDefaults();
    await loadProjectData();
    render();
  });

  window.addEventListener('unhandledrejection', (event) => {
    toast(event.reason?.message || 'Something went wrong.', 'error');
  });

  const modal = document.getElementById('modal');
  document.getElementById('modal-close')?.addEventListener('click', () => modal?.close());
  modal?.addEventListener('click', (event) => {
    if (event.target === modal) modal.close();
  });

  const query = window.matchMedia('(prefers-color-scheme: light)');
  const onSystemChange = () => {
    if (state.settings?.appearance?.theme === 'system') {
      applyAppearance(state.settings.appearance);
      renderShell();
    }
  };
  if (query.addEventListener) query.addEventListener('change', onSystemChange);
  mediaQuery = query;
}

/* Fallback: the markup already defines the shell; render once the DOM is ready. */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
