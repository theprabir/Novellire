import { api } from '../api.js';
import {
  closeModal,
  copyText,
  count,
  el,
  emptyState,
  field,
  icon,
  input,
  openModal,
  proseNodes,
  select,
  statusChip,
  textarea,
  toast,
} from '../ui.js';

const TYPE_LABELS = { bible: 'Story bible', characters: 'Characters', chapters: 'Chapters' };
const TYPE_ICONS = { bible: 'file', characters: 'user', chapters: 'layers' };

export function renderWorkspace(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  if (!state.activeProjectId || !state.tree) {
    wrap.append(
      el('div', { class: 'page-head' }, el('div', {}, el('h1', {}, 'Workspace'))),
      emptyState({
        iconName: 'layers',
        title: 'No project selected',
        body: 'Open or create a project to build its story bible, cast, and chapter map.',
        action: el('a', { class: 'btn btn-primary', href: '#/projects' }, 'Go to projects'),
      })
    );
    return wrap;
  }

  const project = state.tree.project;
  const type = TYPE_LABELS[state.workspaceType] ? state.workspaceType : 'chapters';
  const items = workspaceItems(state, type);

  if (!items.some((item) => item.id === state.selectedId)) {
    state.selectedId = items.length ? items[0].id : null;
  }
  if (type === 'chapters') {
    const chapter = findChapter(state, state.selectedId);
    const scenes = chapter?.scenes || [];
    if (!scenes.some((scene) => scene.id === state.selectedSceneId)) {
      state.selectedSceneId = scenes.length ? scenes[0].id : null;
    }
  }

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, project.name),
        el(
          'div',
          { class: 'sub' },
          `${count(state.tree.stats.chapters)} chapters · ${count(state.tree.stats.scenes)} scenes · ${count(state.tree.stats.characters)} characters · ${count(state.tree.stats.words)} drafted words`
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el('span', { class: 'chip' }, project.genre || 'No genre'),
        project.target_word_count
          ? el('span', { class: 'chip' }, `${count(project.target_word_count)} target`)
          : null
      )
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'workspace-toolbar' },
      segmentedTypes(ctx, type),
      el(
        'button',
        {
          class: 'btn btn-primary btn-sm',
          type: 'button',
          onClick: () => openCreateDialog(ctx, type, project.id),
        },
        icon('plus'),
        `New ${type === 'bible' ? 'entry' : type === 'characters' ? 'character' : 'chapter'}`
      )
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'split' },
      listPanel(ctx, type, items),
      editorPanel(ctx, type, project.id)
    )
  );

  return wrap;
}

function segmentedTypes(ctx, active) {
  const wrap = el('div', { class: 'segmented', role: 'group', 'aria-label': 'Workspace section' });
  for (const [key, label] of Object.entries(TYPE_LABELS)) {
    wrap.append(
      el(
        'button',
        {
          type: 'button',
          'aria-pressed': key === active ? 'true' : 'false',
          onClick: () => {
            window.location.hash = `#/workspace/${key}`;
          },
        },
        icon(TYPE_ICONS[key], 'icon'),
        label
      )
    );
  }
  return wrap;
}

function workspaceItems(state, type) {
  if (type === 'bible') {
    return (state.details?.bible || []).map((entry) => ({
      id: entry.id,
      title: entry.title,
      subtitle: categoryLabel(state, entry.category),
    }));
  }
  if (type === 'characters') {
    return (state.details?.characters || []).map((character) => ({
      id: character.id,
      title: character.name,
      subtitle: character.aliases.length ? `aka ${character.aliases.join(', ')}` : character.personality || 'No profile yet',
    }));
  }
  return (state.manuscript?.chapters || []).map((chapter) => ({
    id: chapter.id,
    title: `${chapter.position}. ${chapter.title}`,
    subtitle: `${chapter.scenes.length} scene${chapter.scenes.length === 1 ? '' : 's'} · ${count(chapter.word_count)} words`,
    status: chapter.status,
  }));
}

function listPanel(ctx, type, items) {
  const search = input({ placeholder: `Search ${TYPE_LABELS[type].toLowerCase()}…`, type: 'search' });
  const rows = el('div', { class: 'list-scroll' });

  const renderRows = (filter = '') => {
    rows.replaceChildren();
    const needle = filter.trim().toLowerCase();
    const visible = items.filter(
      (item) =>
        !needle ||
        item.title.toLowerCase().includes(needle) ||
        (item.subtitle || '').toLowerCase().includes(needle)
    );
    if (!visible.length) {
      rows.append(el('div', { class: 'tree-empty' }, items.length ? 'No matches' : 'Nothing here yet'));
      return;
    }
    for (const item of visible) {
      rows.append(
        el(
          'button',
          {
            class: 'list-row',
            type: 'button',
            'aria-current': item.id === ctx.state.selectedId ? 'true' : undefined,
            onClick: () => {
              ctx.state.selectedId = item.id;
              window.location.hash = `#/workspace/${type}/${item.id}`;
            },
          },
          icon(TYPE_ICONS[type], 'icon sm'),
          el(
            'span',
            { class: 'texts' },
            el('span', { class: 'name' }, item.title),
            item.subtitle ? el('span', { class: 'sub' }, item.subtitle) : null
          ),
          item.status ? statusChip(item.status, ctx.state.meta) : null
        )
      );
    }
  };

  search.addEventListener('input', () => renderRows(search.value));
  renderRows();

  return el(
    'div',
    { class: 'list-panel' },
    el('div', { class: 'list-panel-head' }, field(`All ${TYPE_LABELS[type].toLowerCase()}`, search)),
    rows
  );
}

function editorPanel(ctx, type, projectId) {
  const { state } = ctx;
  if (!state.selectedId) {
    return el(
      'div',
      { class: 'editor-panel' },
      emptyState({
        iconName: TYPE_ICONS[type],
        title: `No ${TYPE_LABELS[type].toLowerCase()} yet`,
        body:
          type === 'chapters'
            ? 'Create a chapter to start the chapter map. Scenes live inside chapters and hold the prose.'
            : 'Add the first entry so the writing workspace has canon to work from.',
        action: el(
          'button',
          { class: 'btn btn-primary btn-sm', type: 'button', onClick: () => openCreateDialog(ctx, type, projectId) },
          icon('plus'),
          'Create'
        ),
      })
    );
  }

  if (type === 'bible') return bibleEditor(ctx, state.details.bible.find((entry) => entry.id === state.selectedId));
  if (type === 'characters') return characterEditor(ctx, state.details.characters.find((item) => item.id === state.selectedId));
  return chapterEditor(ctx, findChapter(state, state.selectedId));
}

function editorHead(eyebrow, title, meta, actions = []) {
  return el(
    'div',
    { class: 'editor-head' },
    el('div', {}, el('div', { class: 'hint' }, eyebrow), el('h2', {}, title), meta ? el('div', { class: 'sub' }, meta) : null),
    el('div', { class: 'actions' }, ...actions)
  );
}

/* -- story bible ---------------------------------------------------------- */

function bibleEditor(ctx, entry) {
  const { state } = ctx;
  const category = select(
    state.meta.bible_categories.map((item) => ({ value: item.key, label: item.label })),
    { value: entry.category }
  );
  const title = input({ value: entry.title, maxlength: '200' });
  const content = textarea({ value: entry.content, rows: 16, placeholder: 'Established facts, rules, and details…' });

  const form = el(
    'form',
    { class: 'card form-card form-grid' },
    el('div', { class: 'span-2' }, field('Category', category)),
    el('div', { class: 'span-2' }, field('Title', title)),
    el('div', { class: 'span-2' }, field('Content', content, 'Canon text. Later phases retrieve this automatically when writing.')),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save entry'),
      el('span', { class: 'hint' }, `Updated ${entry.updated_at ? new Date(entry.updated_at).toLocaleString() : '—'}`)
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api.patch(`/api/bible/${entry.id}`, {
        category: category.value,
        title: title.value,
        content: content.value,
      });
      await ctx.refresh();
      toast('Story bible entry saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  return el(
    'div',
    { class: 'editor-panel' },
    editorHead(categoryLabel(state, entry.category), entry.title, `Entry #${entry.id}`, [
      el('span', { class: 'chip' }, categoryLabel(state, entry.category)),
    ]),
    form
  );
}

function openBibleCreateDialog(ctx, projectId) {
  const { state } = ctx;
  const category = select(state.meta.bible_categories.map((item) => ({ value: item.key, label: item.label })));
  const title = input({ placeholder: 'The dying star', maxlength: '200' });
  const content = textarea({ rows: 8, placeholder: 'What is established about this part of the world?' });

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Category', category)),
    el('div', { class: 'span-2' }, field('Title', title)),
    el('div', { class: 'span-2' }, field('Content', content)),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Add entry'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const created = await api.post(`/api/projects/${projectId}/bible`, {
        category: category.value,
        title: title.value,
        content: content.value,
      });
      ctx.state.selectedId = created.id;
      closeModal();
      await ctx.refresh();
      syncHash(`#/workspace/bible/${created.id}`);
      toast('Entry added.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  openModal({ title: 'New story bible entry', body: form });
}

/* -- characters ----------------------------------------------------------- */

function characterEditor(ctx, character) {
  const { state } = ctx;
  const name = input({ value: character.name, maxlength: '120' });
  const aliases = input({ value: character.aliases.join(', '), placeholder: 'M, the Courier' });

  const profileInputs = new Map();
  const profileNodes = state.meta.character_fields.map((definition) => {
    const control = textarea({
      value: character[definition.key] || '',
      rows: 3,
      placeholder: '',
    });
    profileInputs.set(definition.key, control);
    return field(definition.label, control);
  });

  const form = el(
    'form',
    { class: 'card form-card form-grid' },
    field('Name', name),
    field('Aliases', aliases, 'Comma separated. Used later for entity matching.'),
    ...profileNodes,
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save character'),
      el('span', { class: 'hint' }, 'Identity only. Current location and knowledge arrive with narrative state (Phase 5).')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const profile = {};
    for (const [key, control] of profileInputs.entries()) profile[key] = control.value;
    try {
      await api.patch(`/api/characters/${character.id}`, { name: name.value, ...profile });
      await api.put(`/api/characters/${character.id}/aliases`, {
        aliases: aliases.value.split(',').map((value) => value.trim()).filter(Boolean),
      });
      await ctx.refresh();
      toast('Character saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  return el(
    'div',
    { class: 'editor-panel' },
    editorHead('Character', character.name, character.aliases.length ? `aka ${character.aliases.join(', ')}` : 'No aliases', [
      el('span', { class: 'chip' }, 'Profile'),
    ]),
    form
  );
}

function openCharacterCreateDialog(ctx, projectId) {
  const { state } = ctx;
  const name = input({ placeholder: 'Mira Voss', maxlength: '120' });
  const aliases = input({ placeholder: 'M, the Courier' });
  const profileInputs = new Map();
  const profileNodes = state.meta.character_fields.map((definition) => {
    const control = textarea({ rows: 2 });
    profileInputs.set(definition.key, control);
    return field(definition.label, control);
  });

  const form = el(
    'form',
    { class: 'form-grid' },
    field('Name', name),
    field('Aliases', aliases, 'Comma separated.'),
    ...profileNodes,
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Add character'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const profile = {};
    for (const [key, control] of profileInputs.entries()) profile[key] = control.value;
    try {
      const created = await api.post(`/api/projects/${projectId}/characters`, {
        name: name.value,
        aliases: aliases.value.split(',').map((value) => value.trim()).filter(Boolean),
        ...profile,
      });
      ctx.state.selectedId = created.id;
      closeModal();
      await ctx.refresh();
      syncHash(`#/workspace/characters/${created.id}`);
      toast('Character added.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  openModal({ title: 'New character', body: form });
}

/* -- chapters and scenes -------------------------------------------------- */

function findChapter(state, chapterId) {
  return (state.manuscript?.chapters || []).find((chapter) => chapter.id === chapterId);
}

function chapterEditor(ctx, chapter) {
  if (!chapter) return el('div', { class: 'editor-panel' });
  const { state } = ctx;
  const title = input({ value: chapter.title, maxlength: '200' });
  const part = input({ value: chapter.part, maxlength: '120', placeholder: 'Act One' });
  const summary = textarea({ value: chapter.summary, rows: 3 });
  const objectives = textarea({ value: chapter.objectives, rows: 3 });
  const target = input({ type: 'number', min: '0', max: '100000', step: '500', value: String(chapter.target_word_count || 0) });
  const status = select(
    state.meta.work_statuses.map((item) => ({ value: item.key, label: item.label })),
    { value: chapter.status, class: 'select status-select' }
  );
  const viewpoint = select(
    [{ value: '', label: 'No viewpoint set' }, ...state.details.characters.map((character) => ({ value: String(character.id), label: character.name }))],
    { value: chapter.viewpoint_character_id ? String(chapter.viewpoint_character_id) : '' }
  );

  const form = el(
    'form',
    { class: 'card form-card form-grid' },
    el('div', { class: 'span-2' }, field('Chapter title', title)),
    field('Part or act', part),
    field('Status', status),
    field('Viewpoint character', viewpoint),
    field('Target words', target),
    el('div', { class: 'span-2' }, field('Summary', summary, 'What this chapter must accomplish.')),
    el('div', { class: 'span-2' }, field('Objectives and required developments', objectives)),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save chapter'),
      el('span', { class: 'hint' }, `${chapter.scenes.length} scenes · ${count(chapter.word_count)} drafted words`)
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api.patch(`/api/chapters/${chapter.id}`, {
        title: title.value,
        part: part.value,
        summary: summary.value,
        objectives: objectives.value,
        status: status.value,
        viewpoint_character_id: viewpoint.value ? Number(viewpoint.value) : null,
        target_word_count: Number(target.value) || null,
      });
      await ctx.refresh();
      toast('Chapter saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  const scene = chapter.scenes.find((item) => item.id === state.selectedSceneId);

  return el(
    'div',
    { class: 'editor-panel' },
    editorHead(`Chapter ${chapter.position}`, chapter.title, `${count(chapter.word_count)} words · ${chapter.scenes.length} scenes`, [
      statusChip(chapter.status, state.meta),
      el('a', { class: 'btn btn-sm', href: `#/preview/${chapter.id}` }, icon('book'), 'Read'),
    ]),
    form,
    scenesSection(ctx, chapter, scene)
  );
}

function scenesSection(ctx, chapter, scene) {
  const { state } = ctx;
  const stack = el('div', { class: 'scene-stack' });
  if (!chapter.scenes.length) {
    stack.append(el('p', { class: 'hint' }, 'No scenes yet. Add a scene to hold the prose for this chapter.'));
  }
  for (const item of chapter.scenes) {
    stack.append(
      el(
        'div',
        { class: 'scene-row' },
        el('span', { class: 'index' }, String(item.position).padStart(2, '0')),
        el('span', { class: 'name' }, item.title || 'Untitled scene'),
        el('span', { class: 'excerpt' }, item.content ? item.content.slice(0, 90).replace(/\s+/g, ' ') : 'Empty scene'),
        statusChip(item.status, state.meta),
        el('span', { class: 'meta' }, `${count(item.word_count)} w`),
        el(
          'button',
          {
            class: 'btn btn-sm',
            type: 'button',
            onClick: () => {
              ctx.state.selectedSceneId = item.id;
              syncHash(`#/workspace/chapters/${chapter.id}`);
              ctx.render();
            },
          },
          'Edit'
        )
      )
    );
  }

  const header = el(
    'div',
    { class: 'editor-toolbar' },
    el('div', { class: 'left' }, icon('file'), el('strong', {}, 'Scenes'), el('span', { class: 'hint' }, 'Prose is saved per scene.')),
    el(
      'div',
      { class: 'right' },
      el(
        'button',
        { class: 'btn btn-sm', type: 'button', onClick: () => openSceneCreateDialog(ctx, chapter.id) },
        icon('plus'),
        'Add scene'
      )
    )
  );

  const wrapper = el('div', { class: 'card card-pad' }, header, stack);
  if (scene) wrapper.append(sceneEditor(ctx, chapter, scene));
  return wrapper;
}

function sceneEditor(ctx, chapter, scene) {
  const { state } = ctx;
  const title = input({ value: scene.title, maxlength: '200', placeholder: 'Untitled scene' });
  const summary = textarea({ value: scene.summary, rows: 2 });
  const objectives = textarea({ value: scene.objectives, rows: 2 });
  const content = textarea({ value: scene.content, rows: 16, class: 'textarea prose' });
  const status = select(
    state.meta.work_statuses.map((item) => ({ value: item.key, label: item.label })),
    { value: scene.status, class: 'select status-select' }
  );

  const form = el(
    'form',
    { class: 'scene-editor form-grid', style: { marginTop: '16px', borderTop: '1px solid var(--border)', paddingTop: '16px' } },
    el('div', { class: 'span-2' }, field('Scene title', title)),
    field('Status', status),
    field('Summary', summary),
    el('div', { class: 'span-2' }, field('Objectives', objectives)),
    el(
      'div',
      { class: 'span-2' },
      el(
        'div',
        { class: 'editor-toolbar', style: { marginBottom: '6px' } },
        el('label', { class: 'label' }, 'Scene text'),
        el(
          'div',
          { class: 'right' },
          el('span', { class: 'hint' }, `${count(scene.word_count)} words`),
          el('button', { class: 'btn btn-sm', type: 'button', onClick: () => copyText(content.value) }, icon('copy'), 'Copy'),
          el(
            'button',
            {
              class: 'btn btn-sm',
              type: 'button',
              onClick: () => openGenerateDialog(ctx, chapter, scene),
            },
            icon('wand'),
            'Generate draft'
          )
        )
      ),
      content
    ),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save scene'),
      el('span', { class: 'hint' }, 'Generation never overwrites automatically — insert a draft yourself.')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api.patch(`/api/scenes/${scene.id}`, {
        title: title.value,
        summary: summary.value,
        objectives: objectives.value,
        content: content.value,
        status: status.value,
      });
      await ctx.refresh();
      toast('Scene saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  return form;
}

function openChapterCreateDialog(ctx, projectId) {
  const { state } = ctx;
  const title = input({ placeholder: 'The Sealed Vault', maxlength: '200' });
  const part = input({ placeholder: 'Act One', maxlength: '120' });
  const summary = textarea({ rows: 3 });
  const objectives = textarea({ rows: 3 });
  const viewpoint = select(
    [{ value: '', label: 'No viewpoint set' }, ...state.details.characters.map((character) => ({ value: String(character.id), label: character.name }))],
    { value: '' }
  );
  const target = input({ type: 'number', min: '0', max: '100000', step: '500', value: '2500' });

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Chapter title', title)),
    field('Part or act', part),
    field('Viewpoint character', viewpoint),
    field('Target words', target),
    el('div', { class: 'span-2' }, field('Summary', summary)),
    el('div', { class: 'span-2' }, field('Objectives and required developments', objectives)),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Add chapter'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const created = await api.post(`/api/projects/${projectId}/chapters`, {
        title: title.value,
        part: part.value,
        summary: summary.value,
        objectives: objectives.value,
        viewpoint_character_id: viewpoint.value ? Number(viewpoint.value) : null,
        target_word_count: Number(target.value) || null,
      });
      ctx.state.selectedId = created.id;
      ctx.state.selectedSceneId = null;
      closeModal();
      await ctx.refresh();
      syncHash(`#/workspace/chapters/${created.id}`);
      toast('Chapter added.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  openModal({ title: 'New chapter', body: form });
}

function openSceneCreateDialog(ctx, chapterId) {
  const { state } = ctx;
  const title = input({ placeholder: 'Approach', maxlength: '200' });
  const summary = textarea({ rows: 2 });
  const objectives = textarea({ rows: 2 });
  const content = textarea({ rows: 6, placeholder: 'Optional starting prose.' });
  const status = select(
    state.meta.work_statuses.map((item) => ({ value: item.key, label: item.label })),
    { value: 'planned' }
  );

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Scene title', title)),
    field('Status', status),
    field('Summary', summary),
    el('div', { class: 'span-2' }, field('Objectives', objectives)),
    el('div', { class: 'span-2' }, field('Starting text', content)),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Add scene'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const created = await api.post(`/api/chapters/${chapterId}/scenes`, {
        title: title.value,
        summary: summary.value,
        objectives: objectives.value,
        content: content.value,
        status: status.value,
      });
      ctx.state.selectedSceneId = created.id;
      closeModal();
      await ctx.refresh();
      toast('Scene added.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  openModal({ title: 'New scene', body: form });
}

/* -- generation ----------------------------------------------------------- */

function openGenerateDialog(ctx, chapter, scene) {
  const { state } = ctx;
  const models = (state.ollama?.models || []).map((model) => model.name);
  const saved = state.settings.generation;
  const preferred = models.includes(saved.model) ? saved.model : models[0] || '';

  const model = select(
    models.length
      ? models.map((name) => ({ value: name, label: name }))
      : [{ value: '', label: 'No models installed' }],
    { value: preferred }
  );
  const instructions = textarea({
    rows: 4,
    placeholder: 'What happens in this scene? Who is present, what changes, what must be true by the end?',
  });
  const targetWords = input({ type: 'number', min: '200', max: '2000', step: '50', value: '900' });
  const notes = textarea({ rows: 2, placeholder: 'Details the model must honour: names, objects, prior events.' });
  const temperature = input({ type: 'range', min: '0', max: '2', step: '0.05', value: String(saved.temperature) });
  const temperatureValue = el('span', { class: 'chip' }, Number(saved.temperature).toFixed(2));
  temperature.addEventListener('input', () => { temperatureValue.textContent = Number(temperature.value).toFixed(2); });
  const topP = input({ type: 'range', min: '0.05', max: '1', step: '0.05', value: String(saved.top_p) });
  const topPValue = el('span', { class: 'chip' }, Number(saved.top_p).toFixed(2));
  topP.addEventListener('input', () => { topPValue.textContent = Number(topP.value).toFixed(2); });
  const numPredict = input({ type: 'number', min: '32', max: '8192', step: '1', value: String(saved.num_predict) });
  const contextWindow = select([2048, 4096, 8192].map((value) => ({ value: String(value), label: `${value} tokens` })), { value: String(saved.context_window) });

  const submit = el(
    'button',
    { class: 'btn btn-primary', type: 'submit' },
    icon('wand'),
    'Generate'
  );
  if (!preferred) {
    submit.disabled = true;
    submit.title = 'Install a model first';
  }

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Instructions', instructions)),
    field('Model', model),
    field('Target words', targetWords),
    el('div', { class: 'span-2' }, field('Context notes', notes)),
    el(
      'details',
      { class: 'span-2', style: { borderTop: '1px dashed var(--border)', paddingTop: '10px' } },
      el('summary', { class: 'hint', style: { cursor: 'pointer' } }, 'Advanced parameters'),
      el(
        'div',
        { class: 'form-grid', style: { marginTop: '10px' } },
        el('div', { class: 'field' }, el('label', { class: 'label' }, 'Temperature'), el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } }, temperature, temperatureValue)),
        el('div', { class: 'field' }, el('label', { class: 'label' }, 'Top-p'), el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } }, topP, topPValue)),
        field('Maximum output tokens', numPredict),
        field('Context window', contextWindow)
      )
    ),
    el(
      'div',
      { class: 'form-actions span-2' },
      submit,
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel'),
      !models.length
        ? el('span', { class: 'chip warn' }, 'Start Ollama and pull a model')
        : el('span', { class: 'hint' }, 'One model runs at a time.')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.replaceChildren(icon('refresh'), 'Generating…');
    try {
      const record = await api.post(`/api/projects/${state.activeProjectId}/generate`, {
        instructions: instructions.value,
        model: model.value,
        temperature: Number(temperature.value),
        top_p: Number(topP.value),
        num_predict: Number(numPredict.value),
        context_window: Number(contextWindow.value),
        target_words: Number(targetWords.value),
        chapter_title: chapter.title,
        scene_title: scene.title,
        context_notes: notes.value,
        chapter_id: chapter.id,
        scene_id: scene.id,
      });
      api
        .put('/api/settings/generation', {
          model: model.value,
          temperature: Number(temperature.value),
          top_p: Number(topP.value),
          num_predict: Number(numPredict.value),
          context_window: Number(contextWindow.value),
        })
        .then((settings) => { state.settings.generation = settings; })
        .catch(() => {});
      showGenerationResult(ctx, record, scene);
    } catch (error) {
      toast(error.message, 'error');
      submit.disabled = false;
      submit.replaceChildren(icon('wand'), 'Generate');
    }
  });

  openModal({ title: `Generate — ${scene.title || 'scene'}`, body: form, wide: true });
}

function showGenerationResult(ctx, record, scene) {
  const existing = scene.content || '';
  const output = textarea({ value: record.output, rows: 16, class: 'textarea prose' });
  const append = input({ type: 'checkbox' });
  append.checked = Boolean(existing);

  const seconds = (record.duration_ms / 1000).toFixed(1);
  const body = [
    el(
      'div',
      { class: 'editor-toolbar' },
      el(
        'div',
        { class: 'left' },
        el('span', { class: 'chip accent' }, record.model),
        el('span', { class: 'chip' }, `${count(record.word_count)} words`),
        el('span', { class: 'chip' }, `${seconds}s`),
        record.truncated ? el('span', { class: 'chip warn' }, 'Hit output limit') : null
      ),
      el('span', { class: 'hint' }, 'Edit before inserting if needed. The saved generation log is immutable.')
    ),
    output,
    existing
      ? el(
          'label',
          { class: 'hint', style: { display: 'flex', gap: '8px', alignItems: 'center' } },
          append,
          'Append to existing scene text (otherwise replaces it)'
        )
      : null,
  ];

  const insert = el(
    'button',
    {
      class: 'btn btn-primary',
      type: 'button',
      onClick: async () => {
        const text = output.value.trim();
        if (!text) {
          toast('There is no text to insert.', 'error');
          return;
        }
        insert.disabled = true;
        try {
          const next = append.checked && existing ? `${existing}\n\n${text}` : text;
          await api.patch(`/api/scenes/${scene.id}`, { content: next });
          closeModal();
          await ctx.refresh();
          toast('Draft inserted into the scene.', 'success');
        } catch (error) {
          toast(error.message, 'error');
          insert.disabled = false;
        }
      },
    },
    icon('check'),
    'Insert into scene'
  );

  openModal({
    title: 'Generated draft',
    body,
    wide: true,
    footer: [
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: () => copyText(output.value) }, icon('copy'), 'Copy'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Close'),
      insert,
    ],
  });
}

/* -- shared --------------------------------------------------------------- */

function openCreateDialog(ctx, type, projectId) {
  if (type === 'bible') return openBibleCreateDialog(ctx, projectId);
  if (type === 'characters') return openCharacterCreateDialog(ctx, projectId);
  return openChapterCreateDialog(ctx, projectId);
}

function categoryLabel(state, key) {
  return (state.meta?.bible_categories || []).find((item) => item.key === key)?.label || key;
}

function syncHash(hash) {
  if (window.location.hash !== hash) {
    window.history.replaceState(null, '', hash);
  }
}
