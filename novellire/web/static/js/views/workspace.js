import { api } from '../api.js';
import {
  closeModal,
  confirmDialog,
  count,
  el,
  emptyState,
  field,
  formatDate,
  icon,
  input,
  openModal,
  select,
  textarea,
  toast,
} from '../ui.js';

const DOCUMENT_ICONS = {
  master_bible: 'file',
  character_bible: 'user',
  chapter_map: 'layers',
  style_guide: 'feather',
};

export function renderWorkspace(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  if (!state.activeProjectId || !state.tree) {
    wrap.append(
      el('div', { class: 'page-head' }, el('div', {}, el('h1', {}, 'Workspace'))),
      emptyState({
        iconName: 'layers',
        title: 'No project selected',
        body: 'Open or create a project to write its story bible, character bible, chapter map, and style guide.',
        action: el('a', { class: 'btn btn-primary', href: '#/projects' }, 'Go to projects'),
      })
    );
    return wrap;
  }

  const project = state.tree.project;
  const chapters = state.manuscript?.chapters || [];
  const documents = state.documents || [];
  const section = state.workspaceType === 'chapters' ? 'chapters' : 'docs';

  if (section === 'chapters' && !chapters.some((chapter) => chapter.id === state.selectedId)) {
    state.selectedId = chapters.length ? chapters[0].id : null;
  }
  if (section === 'docs' && !documents.some((document) => document.kind === state.selectedDoc)) {
    state.selectedDoc = 'master_bible';
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
          `${count(chapters.length)} chapter${chapters.length === 1 ? '' : 's'} · ${count(state.tree.stats.words)} words written`
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el(
          'a',
          { class: 'btn btn-sm', href: '#/project/settings' },
          icon('settings'),
          'Project settings'
        ),
        project.genre ? el('span', { class: 'chip' }, project.genre) : null,
        project.target_word_count
          ? el('span', { class: 'chip' }, `${count(project.target_word_count)} target`)
          : null
      )
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'split' },
      listPanel(ctx, documents, chapters, section),
      section === 'chapters'
        ? chapterEditor(ctx, chapters.find((chapter) => chapter.id === state.selectedId))
        : documentEditor(ctx, documents.find((document) => document.kind === state.selectedDoc))
    )
  );

  return wrap;
}

/* -- file list ------------------------------------------------------------ */

function listPanel(ctx, documents, chapters, section) {
  const { state } = ctx;
  const panel = el('div', { class: 'list-panel' });
  const docSection = el('div', { class: 'list-section' });
  docSection.append(el('div', { class: 'list-heading' }, el('span', {}, 'Documents')));

  for (const document of documents) {
    const active = section === 'docs' && document.kind === state.selectedDoc;
    docSection.append(
      el(
        'button',
        {
          class: 'list-row',
          type: 'button',
          'aria-current': active ? 'true' : undefined,
          onClick: () => selectDocument(ctx, document.kind),
        },
        icon(DOCUMENT_ICONS[document.kind] || 'file', 'icon sm'),
        el(
          'span',
          { class: 'texts' },
          el('span', { class: 'name' }, document.title),
          el(
            'span',
            { class: 'sub' },
            document.content.trim()
              ? document.derived
                ? 'Learned from your chapters'
                : wordsLabel(document.content)
              : 'Not written yet'
          )
        )
      )
    );
  }

  const chapterSection = el('div', { class: 'list-section' });
  chapterSection.append(
    el(
      'div',
      { class: 'list-heading' },
      el('span', {}, `Chapters · ${chapters.length}`),
      el(
        'button',
        {
          class: 'icon-btn tiny',
          type: 'button',
          title: 'Add chapter',
          'aria-label': 'Add chapter',
          onClick: () => openChapterDialog(ctx),
        },
        icon('plus')
      )
    )
  );

  if (!chapters.length) {
    chapterSection.append(el('div', { class: 'tree-empty' }, 'No chapters yet'));
  }

  for (const chapter of chapters) {
    chapterSection.append(
      el(
        'button',
        {
          class: 'list-row',
          type: 'button',
          'aria-current': section === 'chapters' && chapter.id === state.selectedId ? 'true' : undefined,
          onClick: () => selectChapter(ctx, chapter.id),
        },
        icon('file', 'icon sm'),
        el(
          'span',
          { class: 'texts' },
          el('span', { class: 'name' }, `${chapter.position}. ${chapter.title}`),
          el('span', { class: 'sub' }, `${count(chapter.word_count)} words`)
        ),
        chapter.origin === 'imported'
          ? el('span', { class: 'chip soon' }, 'Pre-written')
          : null
      )
    );
  }

  panel.append(docSection, chapterSection);
  return panel;
}

function selectDocument(ctx, kind) {
  ctx.state.workspaceType = 'docs';
  ctx.state.selectedDoc = kind;
  syncHash(`#/workspace/docs/${kind}`);
  ctx.render();
}

function selectChapter(ctx, chapterId) {
  ctx.state.workspaceType = 'chapters';
  ctx.state.selectedId = chapterId;
  syncHash(`#/workspace/chapters/${chapterId}`);
  ctx.render();
}

/* -- document editor ------------------------------------------------------ */

function documentEditor(ctx, document) {
  const { state } = ctx;
  if (!document) {
    return el(
      'div',
      { class: 'editor-panel' },
      emptyState({
        iconName: 'file',
        title: 'No document selected',
        body: 'Choose one of the four workspace documents.',
      })
    );
  }

  const chaptersWithText = (state.manuscript?.chapters || []).filter((chapter) =>
    chapter.content.trim()
  );
  const words = el('span', { class: 'hint' }, wordsLabel(document.content));
  const text = textarea({
    value: document.content,
    rows: 22,
    class: 'textarea doc-text',
    placeholder: document.placeholder,
  });
  text.addEventListener('input', () => {
    words.textContent = wordsLabel(text.value);
  });

  const actions = [
    el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save document'),
    words,
  ];

  const canAnalyse =
    document.kind === 'style_guide' &&
    chaptersWithText.length > 0 &&
    (!document.content.trim() || document.derived);
  if (canAnalyse) {
    actions.push(
      el(
        'button',
        {
          class: 'btn btn-ghost',
          type: 'button',
          onClick: (event) => analyseStyleGuide(ctx, event.currentTarget),
        },
        icon('sparkles'),
        'Analyse my manuscript'
      )
    );
  }

  const form = el(
    'form',
    { class: 'card form-card' },
    text,
    el('div', { class: 'form-actions' }, ...actions)
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await api.put(`/api/projects/${state.activeProjectId}/documents/${document.kind}`, {
        content: text.value,
      });
      await ctx.refresh();
      toast(`${document.title} saved.`, 'success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });

  return el(
    'div',
    { class: 'editor-panel' },
    el(
      'div',
      { class: 'editor-head' },
      el(
        'div',
        {},
        el('h2', {}, document.title),
        el('div', { class: 'sub' }, document.summary)
      ),
      el(
        'div',
        { class: 'actions' },
        document.derived ? el('span', { class: 'chip accent' }, 'Learned') : null,
        document.updated_at
          ? el('span', { class: 'hint' }, `Saved ${new Date(document.updated_at).toLocaleString()}`)
          : el('span', { class: 'hint' }, 'Not saved yet')
      )
    ),
    form,
    el(
      'p',
      { class: 'hint' },
      document.kind === 'style_guide'
        ? 'Leave this empty and Novellire will learn the style from your chapters before it writes.'
        : 'Write in prose or bullets. These documents are the only context the AI is given.'
    )
  );
}

async function analyseStyleGuide(ctx, button) {
  const state = ctx.state;
  const model =
    state.settings?.generation?.model || state.ollama?.models?.[0]?.name || '';
  button.disabled = true;
  button.replaceChildren(icon('refresh'), 'Reading your chapters…');
  try {
    const result = await api.post(
      `/api/projects/${state.activeProjectId}/style-guide/analyze`,
      { model }
    );
    toast(`Style guide learned from your chapters (${count(result.word_count)} words).`, 'success');
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
    button.disabled = false;
    button.replaceChildren(icon('sparkles'), 'Analyse my manuscript');
  }
}

/* -- chapter editor ------------------------------------------------------- */

function chapterEditor(ctx, chapter) {
  if (!chapter) {
    return el(
      'div',
      { class: 'editor-panel' },
      emptyState({
        iconName: 'file',
        title: 'No chapter selected',
        body: 'Add a chapter, paste one you have already written, or let Novellire draft a new one from your documents.',
        action: el(
          'button',
          { class: 'btn btn-primary btn-sm', type: 'button', onClick: () => openChapterDialog(ctx) },
          icon('plus'),
          'Add chapter'
        ),
      })
    );
  }

  const imported = chapter.origin === 'imported';
  const chapters = ctx.state.manuscript?.chapters || [];
  const index = chapters.findIndex((item) => item.id === chapter.id);
  const scenes =
    ctx.state.tree?.chapters?.find((item) => item.id === chapter.id)?.scenes || [];
  const title = input({ value: chapter.title, maxlength: '200', placeholder: 'Chapter title' });
  const content = textarea({
    value: chapter.content,
    rows: 24,
    class: 'textarea chapter-text',
    placeholder:
      'Write the chapter here, or leave it empty and let Novellire draft it from your documents.',
  });
  const summary = textarea({
    value: chapter.summary || '',
    rows: 3,
    placeholder: 'A short recap of what happens in this chapter.',
  });
  const words = el('span', { class: 'hint' }, `${count(chapter.word_count)} words`);
  content.addEventListener('input', () => {
    words.textContent = `${count(countWords(content.value))} words`;
  });

  const form = el(
    'form',
    { class: 'card form-card form-grid' },
    el('div', { class: 'span-2' }, field('Chapter title', title)),
    el('div', { class: 'span-2' }, content),
    el(
      'div',
      { class: 'span-2' },
      field(
        'Chapter summary',
        summary,
        'Stored with the chapter and searchable in Memory.'
      )
    ),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save chapter'),
      words,
      el(
        'button',
        {
          class: 'btn btn-ghost',
          type: 'button',
          onClick: () => openChapterHistory(ctx, chapter),
        },
        icon('clock'),
        'History'
      ),
      chapter.content.trim()
        ? el(
            'button',
            {
              class: 'btn btn-ghost',
              type: 'button',
              onClick: (event) => summariseChapter(ctx, chapter, event.currentTarget),
            },
            icon('sparkles'),
            'Summarise'
          )
        : null,
      chapter.content.trim()
        ? el(
            'button',
            {
              class: 'btn btn-ghost',
              type: 'button',
              onClick: (event) => extractEvents(ctx, chapter, event.currentTarget),
            },
            icon('database'),
            'Extract events'
          )
        : null,
      imported
        ? el('span', { class: 'chip' }, 'Pre-written')
        : el(
            'button',
            {
              class: 'btn btn-ghost',
              type: 'button',
              onClick: () => openGenerateDialog(ctx, chapter),
            },
            icon('wand'),
            'Draft with AI'
          )
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await api.patch(`/api/chapters/${chapter.id}`, {
        title: title.value,
        content: content.value,
        summary: summary.value,
      });
      await ctx.refresh();
      toast('Chapter saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });

  return el(
    'div',
    { class: 'editor-panel' },
    el(
      'div',
      { class: 'editor-head' },
      el(
        'div',
        {},
        el('h2', {}, `Chapter ${chapter.position}`),
        el(
          'div',
          { class: 'sub' },
          imported
            ? 'Pre-written chapter. Novellire will not change this text; you can still edit it yourself.'
            : 'Written in Novellire. The AI may draft into this chapter.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        imported ? el('span', { class: 'chip soon' }, 'Pre-written') : null,
        el(
          'div',
          { class: 'icon-row' },
          el(
            'button',
            {
              class: 'icon-btn',
              type: 'button',
              title: 'Move chapter up',
              'aria-label': 'Move chapter up',
              disabled: index <= 0,
              onClick: () => moveChapter(ctx, chapter.id, 'up'),
            },
            icon('arrow-up')
          ),
          el(
            'button',
            {
              class: 'icon-btn',
              type: 'button',
              title: 'Move chapter down',
              'aria-label': 'Move chapter down',
              disabled: index < 0 || index >= chapters.length - 1,
              onClick: () => moveChapter(ctx, chapter.id, 'down'),
            },
            icon('arrow-down')
          ),
          el(
            'button',
            {
              class: 'icon-btn danger',
              type: 'button',
              title: 'Delete chapter',
              'aria-label': 'Delete chapter',
              onClick: () => deleteChapter(ctx, chapter),
            },
            icon('trash')
          )
        ),
        el('a', { class: 'btn btn-sm', href: `#/preview/${chapter.id}` }, icon('book'), 'Read')
      )
    ),
    form,
    scenes.length ? scenesCard(ctx, scenes) : null
  );
}

async function openChapterHistory(ctx, chapter) {
  let revisions;
  try {
    revisions = await api.get(`/api/chapters/${chapter.id}/revisions`);
  } catch (error) {
    toast(error.message, 'error');
    return;
  }

  const body = el(
    'div',
    { class: 'revision-list' },
    el(
      'p',
      { class: 'hint' },
      'Revisions are saved automatically when the chapter text changes. Restoring a version first saves the current text here.'
    )
  );

  if (!revisions.length) {
    body.append(
      emptyState({
        iconName: 'clock',
        title: 'No earlier versions yet',
        body: 'Change and save this chapter’s text, and the previous version will appear here.',
      })
    );
  } else {
    for (const revision of revisions) {
      const text = el('pre', { class: 'revision-text' }, 'Loading…');
      const details = el(
        'details',
        { class: 'revision-details' },
        el('summary', {}, 'Preview text'),
        text
      );
      details.addEventListener('toggle', async () => {
        if (!details.open || details.dataset.loaded) return;
        try {
          const full = await api.get(`/api/chapter-revisions/${revision.id}`);
          text.textContent = full.content || '(Empty chapter)'; 
          details.dataset.loaded = 'true';
        } catch (error) {
          text.textContent = error.message;
        }
      });

      const restore = el(
        'button',
        { class: 'btn btn-sm', type: 'button' },
        icon('refresh'),
        'Restore'
      );
      restore.addEventListener('click', async () => {
        restore.disabled = true;
        try {
          await api.post(
            `/api/chapters/${chapter.id}/revisions/${revision.id}/restore`
          );
          modal.close();
          await ctx.refresh();
          toast('Chapter text restored. The previous text is in History.', 'success');
        } catch (error) {
          toast(error.message, 'error');
          restore.disabled = false;
        }
      });

      body.append(
        el(
          'div',
          { class: 'revision-row' },
          el(
            'div',
            { class: 'revision-head' },
            el(
              'div',
              {},
              el('strong', {}, formatDate(revision.created_at)),
              el(
                'div',
                { class: 'revision-meta' },
                `${count(revision.word_count)} words · ${
                  revision.source === 'restore'
                    ? 'before restore'
                    : 'before edit'
                }`
              )
            ),
            restore
          ),
          details
        )
      );
    }
  }

  const modal = openModal({
    title: `History — ${chapter.title}`,
    wide: true,
    body,
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Close'
      ),
    ],
  });
}

async function summariseChapter(ctx, chapter, button) {
  const state = ctx.state;
  const model =
    state.settings?.generation?.model || state.ollama?.models?.[0]?.name || '';
  button.disabled = true;
  button.replaceChildren(icon('refresh'), 'Summarising…');
  try {
    const result = await api.post(`/api/chapters/${chapter.id}/summarize`, { model });
    const total = countWords(result.summary || '');
    toast(`Summary saved (${count(total)} words).`, 'success');
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
    button.disabled = false;
    button.replaceChildren(icon('sparkles'), 'Summarise');
  }
}

async function extractEvents(ctx, chapter, button) {
  const state = ctx.state;
  const model =
    state.settings?.generation?.model || state.ollama?.models?.[0]?.name || '';
  button.disabled = true;
  button.replaceChildren(icon('refresh'), 'Extracting…');
  try {
    const result = await api.post(`/api/chapters/${chapter.id}/events/extract`, {
      model,
    });
    const total = result.events?.length || 0;
    toast(
      total
        ? `${count(total)} event${total === 1 ? '' : 's'} stored for this chapter.`
        : 'No events were found in this chapter.',
      total ? 'success' : 'error'
    );
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
    button.disabled = false;
    button.replaceChildren(icon('database'), 'Extract events');
  }
}

function scenesCard(ctx, scenes) {
  const rows = el('div', { class: 'scene-stack' });
  scenes.forEach((scene, index) => {
    rows.append(
      el(
        'div',
        { class: 'scene-row' },
        el('span', { class: 'index' }, String(scene.position).padStart(2, '0')),
        el('span', { class: 'name' }, scene.title || 'Untitled scene'),
        el('span', { class: 'meta' }, `${count(scene.word_count)} words`),
        el(
          'div',
          { class: 'scene-actions' },
          el(
            'button',
            {
              class: 'icon-btn tiny',
              type: 'button',
              title: 'Move scene up',
              'aria-label': 'Move scene up',
              disabled: index === 0,
              onClick: () => moveScene(ctx, scene.id, 'up'),
            },
            icon('arrow-up')
          ),
          el(
            'button',
            {
              class: 'icon-btn tiny',
              type: 'button',
              title: 'Move scene down',
              'aria-label': 'Move scene down',
              disabled: index === scenes.length - 1,
              onClick: () => moveScene(ctx, scene.id, 'down'),
            },
            icon('arrow-down')
          ),
          el(
            'button',
            {
              class: 'icon-btn tiny danger',
              type: 'button',
              title: 'Delete scene',
              'aria-label': 'Delete scene',
              onClick: () => deleteScene(ctx, scene),
            },
            icon('trash')
          )
        )
      )
    );
  });

  return el(
    'section',
    { class: 'card form-card' },
    el(
      'div',
      { class: 'editor-head' },
      el(
        'div',
        {},
        el('h2', { class: 'section-title' }, 'Scenes'),
        el(
          'p',
          { class: 'hint' },
          'Legacy scene records inside this chapter. Their prose was folded into the chapter text; reorder or remove them here.'
        )
      )
    ),
    rows
  );
}

async function moveChapter(ctx, chapterId, direction) {
  try {
    await api.post(`/api/chapters/${chapterId}/move`, { direction });
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
  }
}

function deleteChapter(ctx, chapter) {
  confirmDialog({
    title: 'Delete chapter',
    message: `“${chapter.title}” and its scene records will be deleted permanently. This cannot be undone.`,
    confirmLabel: 'Delete chapter',
    onConfirm: async () => {
      try {
        await api.del(`/api/chapters/${chapter.id}`);
        ctx.state.selectedId = null;
        syncHash('#/workspace/chapters');
        await ctx.refresh();
        toast('Chapter deleted.', 'success');
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
}

async function moveScene(ctx, sceneId, direction) {
  try {
    await api.post(`/api/scenes/${sceneId}/move`, { direction });
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
  }
}

function deleteScene(ctx, scene) {
  confirmDialog({
    title: 'Delete scene',
    message: `“${scene.title || 'Untitled scene'}” will be deleted permanently. This cannot be undone.`,
    confirmLabel: 'Delete scene',
    onConfirm: async () => {
      try {
        await api.del(`/api/scenes/${scene.id}`);
        await ctx.refresh();
        toast('Scene deleted.', 'success');
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
}

function openChapterDialog(ctx) {
  const title = input({ placeholder: 'The Sealed Vault', maxlength: '200' });
  const content = textarea({
    rows: 12,
    class: 'textarea chapter-text',
    placeholder: 'Paste the full chapter here, or leave empty to draft it with AI later.',
  });

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Chapter title', title)),
    el('div', { class: 'span-2' }, field('Chapter text', content)),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Add chapter'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    ),
    el(
      'p',
      { class: 'hint span-2' },
      'Pasted text is saved as a pre-written chapter. Novellire counts its words and never rewrites it.'
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const pasted = content.value.trim();
      const created = await api.post(`/api/projects/${ctx.state.activeProjectId}/chapters`, {
        title: title.value,
        content: content.value,
        origin: pasted ? 'imported' : 'written',
      });
      ctx.state.workspaceType = 'chapters';
      ctx.state.selectedId = created.id;
      closeModal();
      await ctx.refresh();
      syncHash(`#/workspace/chapters/${created.id}`);
      toast('Chapter added.', 'success');
    } catch (error) {
      toast(error.message, 'error');
      button.disabled = false;
    }
  });

  openModal({ title: 'Add chapter', body: form, wide: true });
}

/* -- generation ----------------------------------------------------------- */

function openGenerateDialog(ctx, chapter) {
  const state = ctx.state;
  const models = (state.ollama?.models || []).map((model) => model.name);
  const saved = state.settings.generation;
  const preferred = models.includes(saved.model) ? saved.model : models[0] || '';

  const instructions = textarea({
    rows: 4,
    placeholder: 'What happens in this chapter? Who changes, and what must be true by the end?',
  });
  const targetWords = input({ type: 'number', min: '200', max: '6000', step: '50', value: '1200' });
  const notes = textarea({ rows: 2, placeholder: 'Anything the model must honour.' });
  const model = select(
    models.length
      ? models.map((name) => ({ value: name, label: name }))
      : [{ value: '', label: 'No models installed' }],
    { value: preferred }
  );
  const temperature = input({ type: 'range', min: '0', max: '2', step: '0.05', value: String(saved.temperature) });
  const temperatureValue = el('span', { class: 'chip' }, Number(saved.temperature).toFixed(2));
  temperature.addEventListener('input', () => { temperatureValue.textContent = Number(temperature.value).toFixed(2); });
  const numPredict = input({ type: 'number', min: '32', max: '8192', step: '1', value: String(saved.num_predict) });
  const contextWindow = select(
    [2048, 4096, 8192].map((value) => ({ value: String(value), label: `${value} tokens` })),
    { value: String(saved.context_window) }
  );

  const submit = el('button', { class: 'btn btn-primary', type: 'submit' }, icon('wand'), 'Generate');
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
      'p',
      { class: 'hint span-2' },
      'Earlier chapters are selected from this project’s Memory and listed with the draft.'
    ),
    el(
      'details',
      { class: 'span-2', style: { borderTop: '1px dashed var(--border)', paddingTop: '10px' } },
      el('summary', { class: 'hint', style: { cursor: 'pointer' } }, 'Advanced parameters'),
      el(
        'div',
        { class: 'form-grid', style: { marginTop: '10px' } },
        el('div', { class: 'field' }, el('label', { class: 'label' }, 'Temperature'), el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px' } }, temperature, temperatureValue)),
        field('Maximum output tokens', numPredict),
        field('Context window', contextWindow)
      )
    ),
    el(
      'div',
      { class: 'form-actions span-2' },
      submit,
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel'),
      !models.length ? el('span', { class: 'chip warn' }, 'Start Ollama and pull a model') : null
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.replaceChildren(icon('refresh'), 'Writing…');
    try {
      const record = await api.post(`/api/projects/${state.activeProjectId}/generate`, {
        instructions: instructions.value,
        model: model.value,
        temperature: Number(temperature.value),
        top_p: Number(saved.top_p),
        num_predict: Number(numPredict.value),
        context_window: Number(contextWindow.value),
        target_words: Number(targetWords.value),
        chapter_title: chapter.title,
        context_notes: notes.value,
        chapter_id: chapter.id,
      });
      api
        .put('/api/settings/generation', {
          model: model.value,
          temperature: Number(temperature.value),
          top_p: Number(saved.top_p),
          num_predict: Number(numPredict.value),
          context_window: Number(contextWindow.value),
        })
        .then((settings) => { state.settings.generation = settings; })
        .catch(() => {});
      showDraft(ctx, record, chapter);
    } catch (error) {
      toast(error.message, 'error');
      submit.disabled = false;
      submit.replaceChildren(icon('wand'), 'Generate');
    }
  });

  openModal({ title: `Draft chapter ${chapter.position}`, body: form, wide: true });
}

function showDraft(ctx, record, chapter) {
  const existing = chapter.content || '';
  const used = record.context?.chapters || [];
  const usedEvents = record.context?.events || [];
  const output = textarea({ value: record.output, rows: 16, class: 'textarea chapter-text' });
  const append = input({ type: 'checkbox' });
  append.checked = Boolean(existing);

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
          await api.patch(`/api/chapters/${chapter.id}`, {
            content: append.checked && existing ? `${existing}\n\n${text}` : text,
          });
          closeModal();
          await ctx.refresh();
          toast('Draft inserted into the chapter.', 'success');
        } catch (error) {
          toast(error.message, 'error');
          insert.disabled = false;
        }
      },
    },
    icon('check'),
    'Insert into chapter'
  );

  openModal({
    title: 'Generated draft',
    body: [
      el(
        'div',
        { class: 'editor-toolbar' },
        el(
          'div',
          { class: 'left' },
          el('span', { class: 'chip accent' }, record.model),
          el('span', { class: 'chip' }, `${count(record.word_count)} words`),
          record.truncated ? el('span', { class: 'chip warn' }, 'Hit output limit') : null,
          record.style_guide_inferred ? el('span', { class: 'chip ok' }, 'Style guide learned') : null
        ),
        el('span', { class: 'hint' }, 'Edit before inserting if needed.')
      ),
      used.length || usedEvents.length ? contextUsed(used, usedEvents) : null,
      output,
      existing
        ? el(
            'label',
            { class: 'hint', style: { display: 'flex', gap: '8px', alignItems: 'center' } },
            append,
            'Append to the existing chapter text (otherwise replaces it)'
          )
        : null,
    ],
    wide: true,
    footer: [
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Close'),
      insert,
    ],
  });
}

function contextUsed(chapters, events) {
  const parts = [];
  if (chapters.length) {
    parts.push(
      el(
        'div',
        { class: 'context-used-group' },
        el('h4', {}, `Chapters (${count(chapters.length)})`),
        ...chapters.map((chapter) =>
          el(
            'div',
            { class: 'context-used-item' },
            el('strong', {}, `Chapter ${chapter.position} — ${chapter.title}`),
            el('p', { class: 'hint' }, chapter.summary || chapter.excerpt)
          )
        )
      )
    );
  }
  if (events.length) {
    parts.push(
      el(
        'div',
        { class: 'context-used-group' },
        el('h4', {}, `Events (${count(events.length)})`),
        ...events.map((event) =>
          el(
            'div',
            { class: 'context-used-item' },
            el(
              'strong',
              {},
              `Chapter ${event.chapter_position} — ${event.chapter_title}`
            ),
            el('p', { class: 'hint' }, event.summary)
          )
        )
      )
    );
  }

  return el(
    'details',
    { class: 'card card-pad context-used' },
    el(
      'summary',
      { class: 'hint' },
      `Earlier context given to the model (${count(chapters.length)} chapter${
        chapters.length === 1 ? '' : 's'
      }, ${count(events.length)} event${events.length === 1 ? '' : 's'})`
    ),
    el('div', { class: 'context-used-list' }, ...parts)
  );
}

/* -- helpers -------------------------------------------------------------- */

function wordsLabel(text) {
  const total = countWords(text);
  return total ? `${count(total)} words` : 'Empty';
}

function countWords(text) {
  const trimmed = String(text || '').trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function syncHash(hash) {
  if (window.location.hash !== hash) {
    window.history.replaceState(null, '', hash);
  }
}
