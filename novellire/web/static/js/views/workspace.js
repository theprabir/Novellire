import { api } from '../api.js';
import { openStateProposalDialog } from './state-proposals.js?v=0.6.1';
import { openRelationshipProposalDialog } from './relationship-proposals.js?v=0.6.1';
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

  if (document.kind === 'chapter_map' && document.content.trim()) {
    actions.push(
      el(
        'button',
        {
          class: 'btn btn-ghost',
          type: 'button',
          onClick: () => openOutlinePreview(ctx),
        },
        icon('layers'),
        'Build chapters'
      )
    );
  }

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

function openOutlinePreview(ctx) {
  const host = el('div', {}, el('p', { class: 'hint' }, 'Reading the Chapter Map…'));
  let ready = false;
  let phase = 'preview';
  let analysisCount = 0;
  const apply = el(
    'button',
    { class: 'btn btn-primary', type: 'button', disabled: true },
    'Create chapters'
  );
  const cancel = el(
    'button',
    { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
    'Cancel'
  );
  const modal = openModal({
    title: 'Build chapters from the Chapter Map',
    wide: true,
    body: host,
    footer: [cancel, apply],
  });

  apply.addEventListener('click', async () => {
    if (phase === 'failed') {
      modal.close();
      return;
    }
    if (!ready || phase !== 'preview') return;
    phase = 'working';
    apply.disabled = true;
    apply.replaceChildren(icon('refresh'), 'Creating…');
    try {
      const result = await api.post(
        `/api/projects/${ctx.state.activeProjectId}/outline/apply`
      );
      ctx.state.workspaceType = 'chapters';
      ctx.state.selectedId = result.created[0]?.id || ctx.state.selectedId;
      if (ctx.state.selectedId) {
        syncHash(`#/workspace/chapters/${ctx.state.selectedId}`);
      }
      if (!analysisCount) {
        modal.close();
        await ctx.refresh();
        toast(
          result.created_count
            ? `${result.created_count} chapter${result.created_count === 1 ? '' : 's'} created.`
            : 'No chapters needed creating.',
          'success'
        );
        return;
      }
      apply.replaceChildren(icon('refresh'), 'Analysing chapters…');
      await analyzeBeforeOutline(ctx, host, apply, analysisCount);
      phase = 'done';
      modal.close();
      await ctx.refresh();
      toast('Written chapters analysed and added to memory.', 'success');
    } catch (error) {
      phase = 'failed';
      apply.disabled = false;
      cancel.hidden = true;
      apply.replaceChildren('Close');
      host.prepend(el('p', { class: 'hint' }, error.message));
      toast(error.message, 'error');
    }
  });

  api
    .get(`/api/projects/${ctx.state.activeProjectId}/outline/preview`)
    .then((preview) => {
      ready = true;
      analysisCount = preview.analysis_count || 0;
      const hasWork = preview.create_count > 0 || analysisCount > 0;
      apply.disabled = !hasWork;
      apply.replaceChildren(
        preview.create_count
          ? `Create ${preview.create_count} chapter${preview.create_count === 1 ? '' : 's'}`
          : analysisCount
            ? 'Analyse written chapters'
            : 'Nothing to do'
      );
      host.replaceChildren(
        el(
          'p',
          { class: 'hint' },
          `${preview.chapters.length} chapters detected · ${preview.create_count} to create · ${preview.existing_count} already exist · ${analysisCount} written chapter${analysisCount === 1 ? '' : 's'} to analyse. Existing chapters are left unchanged.`
        ),
        el(
          'div',
          { class: 'outline-preview' },
          ...preview.chapters.map((chapter) =>
            el(
              'div',
              { class: 'outline-row' },
              el('span', { class: 'chip' }, `Chapter ${chapter.number}`),
              el(
                'div',
                { class: 'texts' },
                el('strong', {}, chapter.title),
                chapter.objectives
                  ? el('span', { class: 'sub' }, chapter.objectives.split('\n')[0])
                  : null
              ),
              el(
                'span',
                { class: chapter.action === 'create' ? 'chip accent' : 'chip soon' },
                chapter.action === 'create' ? 'Will create' : 'Exists'
              )
            )
          )
        )
      );
    })
    .catch((error) => {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
}

async function analyzeBeforeOutline(ctx, host, button, total) {
  const settings = ctx.state.settings?.generation || {};
  const model = settings.model || ctx.state.ollama?.models?.[0]?.name || '';
  const heading = el(
    'p',
    { class: 'hint' },
    `Analysing ${total} written chapter${total === 1 ? '' : 's'} one at a time…`
  );
  const rows = el('div', { class: 'outline-preview' });
  host.replaceChildren(heading, rows);
  button.replaceChildren(icon('refresh'), 'Analysing…');
  let failed = false;
  await api.stream(
    `/api/projects/${ctx.state.activeProjectId}/outline/analyze`,
    {
      model,
      top_p: Number(settings.top_p ?? 0.9),
      num_predict: Number(settings.num_predict ?? 400),
      context_window: Number(settings.context_window ?? 4096),
    },
    (event) => {
      if (event.type === 'start') {
        heading.textContent = `Analysing ${event.total} written chapter${event.total === 1 ? '' : 's'} one at a time…`;
        return;
      }
      if (event.type === 'step') {
        const labels = {
          analysed: 'Added to memory',
          skipped: 'Already stored',
          empty: 'No text',
          failed: 'Failed',
        };
        failed = failed || event.status === 'failed';
        rows.append(
          el(
            'div',
            { class: 'outline-row' },
            el('span', { class: 'chip' }, `Chapter ${event.position}`),
            el(
              'div',
              { class: 'texts' },
              el('strong', {}, event.title),
              el('span', { class: 'sub' }, event.detail || '')
            ),
            el(
              'span',
              {
                class:
                  event.status === 'failed'
                    ? 'chip warn'
                    : event.status === 'analysed'
                      ? 'chip accent'
                      : 'chip soon',
              },
              labels[event.status] || event.status
            )
          )
        );
        heading.textContent = `${event.processed} of ${event.total} written chapters processed.`;
        return;
      }
      if (event.type === 'done') {
        failed = failed || event.failed > 0;
        if (failed) {
          throw new Error('Analysis stopped at a chapter. The rest can be retried later.');
        }
        heading.textContent = `Analysis complete: ${event.analysed} updated, ${event.skipped} already stored, ${event.empty} without text.`;
      }
    }
  );
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
  const approved = chapter.status === 'approved';
  const chapters = ctx.state.manuscript?.chapters || [];
  const index = chapters.findIndex((item) => item.id === chapter.id);
  const scenes =
    ctx.state.tree?.chapters?.find((item) => item.id === chapter.id)?.scenes || [];
  const title = input({ value: chapter.title, maxlength: '200', placeholder: 'Chapter title' });
  const statusOptions = (
    ctx.state.meta?.work_statuses || [
      { key: 'planned', label: 'Planned' },
      { key: 'drafting', label: 'Drafting' },
      { key: 'drafted', label: 'Drafted' },
      { key: 'approved', label: 'Approved' },
    ]
  ).map((item) => ({ value: item.key, label: item.label }));
  const status = select(statusOptions, { value: chapter.status });
  const storyDay = input({
    type: 'number',
    min: '0',
    step: '1',
    value: chapter.story_day ?? '',
    placeholder: 'Optional',
  });
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
  const plan = textarea({
    value: chapter.objectives || '',
    rows: 6,
    placeholder:
      'Optional scene-by-scene plan: titles, purpose, key beats, viewpoint, location.',
  });
  const words = el('span', { class: 'hint' }, `${count(chapter.word_count)} words`);
  content.addEventListener('input', () => {
    words.textContent = `${count(countWords(content.value))} words`;
  });

  const form = el(
    'form',
    { class: 'card form-card form-grid' },
    el('div', {}, field('Chapter title', title)),
    el(
      'div',
      {},
      field(
        'Status',
        status,
        'Approved chapters must be reopened before their text changes.'
      )
    ),
    el(
      'div',
      {},
      field(
        'Story day',
        storyDay,
        'Optional. Days from the story start (0 is the first day) for timeline validation.'
      )
    ),
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
      { class: 'span-2' },
      field(
        'Scene plan',
        plan,
        'Included when Novellire drafts this chapter. Keep it as beats, not prose.'
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
          onClick: () => openChapterHistory(ctx, chapter, content.value),
        },
        icon('clock'),
        'History'
      ),
      !imported
        ? [
            el(
              'button',
              {
                class: 'btn btn-ghost',
                type: 'button',
                onClick: () => openPlanDialog(ctx, chapter, plan.value),
              },
              icon('layers'),
              'Plan with AI'
            ),
            el(
              'button',
              {
                class: 'btn btn-ghost',
                type: 'button',
                onClick: () => openDiscussDialog(ctx, chapter),
              },
              icon('message'),
              'Discuss plan'
            ),
          ]
        : null,
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
        : approved
          ? el(
              'span',
              { class: 'chip ok', title: 'Reopen this chapter to draft into it.' },
              'Approved'
            )
          : [
              el(
                'button',
                {
                  class: 'btn btn-ghost',
                  type: 'button',
                  onClick: () => openGenerateDialog(ctx, chapter),
                },
                icon('wand'),
                'Draft with AI'
              ),
              el(
                'button',
                {
                  class: 'btn btn-ghost',
                  type: 'button',
                  title: 'One inference per beat in the saved scene plan',
                  onClick: (event) => draftSequence(ctx, chapter, event.currentTarget),
                },
                icon('layers'),
                'Draft scene by scene'
              ),
              el(
                'button',
                {
                  class: 'btn btn-ghost',
                  type: 'button',
                  title: 'Check the saved chapter against recorded canon',
                  onClick: () => openContinuityDialog(ctx, chapter),
                },
                icon('shield'),
                'Check continuity'
              ),
              el(
                'button',
                {
                  class: 'btn btn-ghost',
                  type: 'button',
                  title: 'Propose character state changes from this chapter',
                  onClick: () => openStateProposalDialog(ctx, chapter),
                },
                icon('user'),
                'Suggest state updates'
              ),
              el(
                'button',
                {
                  class: 'btn btn-ghost',
                  type: 'button',
                  title: 'Propose relationship changes from this chapter',
                  onClick: () => openRelationshipProposalDialog(ctx, chapter),
                },
                icon('sparkles'),
                'Suggest relationships'
              ),
            ]
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
        objectives: plan.value,
        status: status.value,
        story_day: storyDay.value === '' ? null : Number(storyDay.value),
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

async function openChapterHistory(ctx, chapter, currentText) {
  let revisions;
  try {
    revisions = await api.get(`/api/chapters/${chapter.id}/revisions`);
  } catch (error) {
    toast(error.message, 'error');
    return;
  }

  const draft = typeof currentText === 'string' ? currentText : chapter.content;
  const dirty = draft !== chapter.content;
  const approved = chapter.status === 'approved';
  const body = el('div', { class: 'revision-list' });

  body.append(
    el(
      'p',
      { class: 'hint' },
      'Revisions are saved automatically when the chapter text changes. The newest 50 are kept, and restoring a version first saves the current text here.'
    )
  );
  if (dirty) {
    body.append(
      el(
        'p',
        { class: 'revision-warning' },
        'You have unsaved changes. Save the chapter before restoring an older version.'
      )
    );
  }
  if (approved) {
    body.append(
      el(
        'p',
        { class: 'revision-warning' },
        'This chapter is approved. Reopen it before restoring older text.'
      )
    );
  }

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
      const compareHost = el(
        'div',
        { class: 'revision-compare' },
        el('p', { class: 'hint' }, 'Loading comparison…')
      );
      const details = el(
        'details',
        { class: 'revision-details' },
        el('summary', {}, 'Compare with current draft'),
        compareHost
      );
      let compared = false;
      details.addEventListener('toggle', async () => {
        if (!details.open || compared) return;
        compared = true;
        try {
          const full = await api.get(
            `/api/chapters/${chapter.id}/revisions/${revision.id}`
          );
          renderRevisionComparison(compareHost, full.content || '', draft);
        } catch (error) {
          compared = false;
          compareHost.replaceChildren(el('p', { class: 'hint' }, error.message));
        }
      });

      const restore = el(
        'button',
        { class: 'btn btn-sm', type: 'button', disabled: dirty || approved },
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
          restore.disabled = dirty || approved;
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

const DIFF_CELL_BUDGET = 1_500_000;

function renderRevisionComparison(host, revisionText, currentText) {
  const segments = buildDiffSegments(revisionText, currentText);
  const changed = segments.some((segment) => segment.kind !== 'same');
  const older = el('pre', { class: 'diff-pane' });
  const current = el('pre', { class: 'diff-pane' });
  appendDiffPane(older, segments, 'older');
  appendDiffPane(current, segments, 'current');

  host.replaceChildren(
    changed
      ? el(
          'div',
          { class: 'diff-legend' },
          el('span', { class: 'diff-key diff-key-del' }, 'Removed from this draft'),
          el('span', { class: 'diff-key diff-key-add' }, 'Added in the current draft'),
        )
      : el('p', { class: 'hint' }, 'This revision matches the current draft.'),
    el(
      'div',
      { class: 'diff-grid' },
      el(
        'div',
        { class: 'diff-column' },
        el(
          'div',
          { class: 'diff-title' },
          `This revision · ${count(countWords(revisionText))} words`
        ),
        older
      ),
      el(
        'div',
        { class: 'diff-column' },
        el(
          'div',
          { class: 'diff-title' },
          `Current draft · ${count(countWords(currentText))} words`
        ),
        current
      )
    )
  );
}

function appendDiffPane(pane, segments, side) {
  const fragment = document.createDocumentFragment();
  for (const segment of segments) {
    if (segment.kind === 'same') {
      fragment.append(document.createTextNode(segment.text));
    } else if (
      (side === 'older' && segment.kind === 'del') ||
      (side === 'current' && segment.kind === 'add')
    ) {
      fragment.append(
        el(
          'mark',
          { class: side === 'older' ? 'diff-del' : 'diff-add' },
          segment.text
        )
      );
    }
  }
  if (!fragment.childNodes.length) {
    fragment.append(document.createTextNode('(Empty chapter)'));
  }
  pane.replaceChildren(fragment);
}

function tokenizeWords(text) {
  return text.match(/\S+\s*/g) || [];
}

function buildDiffSegments(beforeText, afterText) {
  const before = tokenizeWords(beforeText);
  const after = tokenizeWords(afterText);
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) {
    prefix += 1;
  }
  let endBefore = before.length;
  let endAfter = after.length;
  while (
    endBefore > prefix &&
    endAfter > prefix &&
    before[endBefore - 1] === after[endAfter - 1]
  ) {
    endBefore -= 1;
    endAfter -= 1;
  }

  const segments = [];
  const push = (kind, text) => {
    if (!text) return;
    const last = segments[segments.length - 1];
    if (last && last.kind === kind) last.text += text;
    else segments.push({ kind, text });
  };
  push('same', before.slice(0, prefix).join(''));

  const oldMiddle = before.slice(prefix, endBefore);
  const newMiddle = after.slice(prefix, endAfter);
  if (oldMiddle.length * newMiddle.length > DIFF_CELL_BUDGET) {
    // A full rewrite: highlighting the whole middle is truthful and stays fast.
    push('del', oldMiddle.join(''));
    push('add', newMiddle.join(''));
  } else {
    const lengths = new Array(oldMiddle.length + 1);
    for (let i = 0; i < lengths.length; i += 1) {
      lengths[i] = new Uint32Array(newMiddle.length + 1);
    }
    for (let i = oldMiddle.length - 1; i >= 0; i -= 1) {
      for (let j = newMiddle.length - 1; j >= 0; j -= 1) {
        lengths[i][j] =
          oldMiddle[i] === newMiddle[j]
            ? lengths[i + 1][j + 1] + 1
            : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < oldMiddle.length && j < newMiddle.length) {
      if (oldMiddle[i] === newMiddle[j]) {
        push('same', oldMiddle[i]);
        i += 1;
        j += 1;
      } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
        push('del', oldMiddle[i]);
        i += 1;
      } else {
        push('add', newMiddle[j]);
        j += 1;
      }
    }
    while (i < oldMiddle.length) push('del', oldMiddle[i++]);
    while (j < newMiddle.length) push('add', newMiddle[j++]);
  }

  push('same', before.slice(endBefore).join(''));
  return segments;
}

function openPlanDialog(ctx, chapter, currentPlan) {
  const state = ctx.state;
  const settings = state.settings?.generation || {};
  const instructions = textarea({
    rows: 3,
    placeholder:
      'Optional focus, such as “four scenes, end on the gate opening” or “make room for Orin’s betrayal”.',
  });
  const output = textarea({
    value: currentPlan || '',
    rows: 14,
    placeholder: 'Generate a plan, then edit it before using it.',
  });
  const generate = el(
    'button',
    { class: 'btn btn-primary', type: 'button' },
    icon('sparkles'),
    'Generate plan'
  );
  const use = el(
    'button',
    { class: 'btn', type: 'button', disabled: !output.value.trim() },
    icon('check'),
    'Use plan'
  );
  const modal = openModal({
    title: `Plan chapter ${chapter.position}`,
    wide: true,
    body: [
      field(
        'Planning instructions',
        instructions,
        'Optional. The chapter summary, scene plan, documents, and retrieved memory are included automatically.'
      ),
      field(
        'Proposed scene plan',
        output,
        'Not saved until you choose Use plan. Once saved, it is included when drafting this chapter.'
      ),
    ],
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Cancel'
      ),
      generate,
      use,
    ],
  });

  generate.addEventListener('click', async () => {
    const model =
      settings.model || state.ollama?.models?.[0]?.name || '';
    if (!model) {
      toast('Choose a model in Settings before planning.', 'error');
      return;
    }
    generate.disabled = true;
    generate.replaceChildren(icon('refresh'), 'Planning…');
    try {
      const record = await api.post(`/api/chapters/${chapter.id}/plan`, {
        instructions: instructions.value,
        model,
        temperature: Number(settings.temperature ?? 0.6),
        top_p: Number(settings.top_p ?? 0.9),
        num_predict: Number(settings.num_predict ?? 700),
        context_window: Number(settings.context_window ?? 4096),
      });
      output.value = record.output || '';
      use.disabled = !output.value.trim();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      generate.disabled = false;
      generate.replaceChildren(icon('sparkles'), 'Generate plan');
    }
  });

  use.addEventListener('click', async () => {
    const text = output.value.trim();
    if (!text) {
      toast('Generate or write a plan first.', 'error');
      return;
    }
    use.disabled = true;
    try {
      await api.patch(`/api/chapters/${chapter.id}`, { objectives: text });
      modal.close();
      await ctx.refresh();
      toast('Scene plan saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
      use.disabled = false;
    }
  });
}

function openDiscussDialog(ctx, chapter) {
  if (!(chapter.objectives || '').trim()) {
    toast('Add a scene plan to this chapter, or use Plan with AI first.', 'error');
    return;
  }
  const state = ctx.state;
  const settings = state.settings?.generation || {};
  const model = settings.model || state.ollama?.models?.[0]?.name || '';
  const host = el('div', { class: 'review-findings' });
  const draft = el(
    'button',
    { class: 'btn btn-primary', type: 'button', disabled: true },
    icon('layers'),
    'Draft with answers'
  );
  let collected = [];
  const modal = openModal({
    title: `Discuss chapter ${chapter.position}`,
    wide: true,
    body: [
      el(
        'p',
        { class: 'hint' },
        'Novellire compares the saved scene plan with the summary, documents, and memory, and asks what it still needs to know. Answers go to the draft only; the plan is not changed.'
      ),
      host,
    ],
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Close'
      ),
      draft,
    ],
  });
  draft.addEventListener('click', () => {
    const instructions = collected
      .filter((item) => item.answer.value.trim())
      .map((item) => `Q: ${item.question}\nA: ${item.answer.value.trim()}`)
      .join('\n\n');
    modal.close();
    draftSequence(ctx, chapter, null, { instructions });
  });

  const render = (result) => {
    const questions = result.questions || [];
    collected = questions.map((item) => ({
      question: item.question,
      answer: textarea({ rows: 2, placeholder: 'Your answer (optional)' }),
    }));
    host.replaceChildren(
      el(
        'p',
        {},
        result.summary ||
          (result.ready
            ? 'The plan looks ready to draft.'
            : 'The plan needs a few decisions before drafting.')
      ),
      questions.length
        ? el(
            'div',
            { class: 'review-list' },
            collected.map((item, index) =>
              el(
                'div',
                { class: 'review-finding' },
                el(
                  'div',
                  { class: 'review-finding-head' },
                  el('span', { class: 'chip accent' }, `Question ${index + 1}`),
                  el('strong', {}, item.question)
                ),
                questions[index].why
                  ? el('p', { class: 'hint' }, questions[index].why)
                  : null,
                item.answer
              )
            )
          )
        : el(
            'p',
            { class: 'hint' },
            'Nothing to clarify. Draft when you are ready.'
          )
    );
    draft.disabled = false;
  };

  if (!model) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Choose a model in Settings before discussing a plan.')
    );
    return;
  }
  host.replaceChildren(el('p', { class: 'hint' }, 'Reading the plan…'));
  api
    .post(`/api/chapters/${chapter.id}/discuss`, {
      model,
      temperature: Number(settings.temperature ?? 0.3),
      top_p: Number(settings.top_p ?? 0.9),
      num_predict: Number(settings.num_predict ?? 700),
      context_window: Number(settings.context_window ?? 4096),
    })
    .then(render)
    .catch((error) => {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
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
  const position = input({
    type: 'number',
    min: '1',
    step: '1',
    placeholder: 'Next chapter',
  });
  const content = textarea({
    rows: 12,
    class: 'textarea chapter-text',
    placeholder: 'Paste the full chapter here, or leave empty to draft it with AI later.',
  });

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Chapter title', title)),
    el(
      'div',
      { class: 'span-2' },
      field(
        'Chapter number',
        position,
        'Optional. Leave blank to add at the end; existing chapters shift down.'
      )
    ),
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
      const number = position.value.trim() ? Number(position.value) : null;
      const created = await api.post(`/api/projects/${ctx.state.activeProjectId}/chapters`, {
        title: title.value.trim() || (number ? `Chapter ${number}` : ''),
        position: number || undefined,
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

async function draftSequence(ctx, chapter, button, { instructions = '' } = {}) {
  const state = ctx.state;
  if (!(chapter.objectives || '').trim()) {
    toast('Add a scene plan to this chapter, or use Plan with AI first.', 'error');
    return;
  }
  const models = (state.ollama?.models || []).map((model) => model.name);
  const saved = state.settings.generation;
  const model = models.includes(saved.model) ? saved.model : models[0] || '';
  if (!model) {
    toast('Choose a model in Settings first.', 'error');
    return;
  }
  if (button) {
    button.disabled = true;
    button.replaceChildren(icon('refresh'), 'Drafting scenes…');
  }
  try {
    const record = await api.post(`/api/chapters/${chapter.id}/draft-sequence`, {
      model,
      instructions,
      target_words: Number(chapter.target_word_count || 1200),
      temperature: Number(saved.temperature),
      top_p: Number(saved.top_p),
      num_predict: Number(saved.num_predict),
      context_window: Number(saved.context_window),
    });
    const scenes = record.scenes?.length || 0;
    toast(
      `Drafted ${scenes} scene${scenes === 1 ? '' : 's'}. Review before inserting.`,
      'success'
    );
    showDraft(ctx, record, chapter);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    if (button) {
      button.disabled = false;
      button.replaceChildren(icon('layers'), 'Draft scene by scene');
    }
  }
}

function openContinuityDialog(ctx, chapter) {
  const state = ctx.state;
  const settings = state.settings?.generation || {};
  const model = settings.model || state.ollama?.models?.[0]?.name || '';
  const host = el('div', { class: 'review-findings' });
  const modal = openModal({
    title: `Continuity · chapter ${chapter.position}`,
    wide: true,
    body: [
      el(
        'p',
        { class: 'hint' },
        'Compares the saved chapter with its character state, approved relationships, extracted events, and story bible. Every finding cites the record it contradicts and quotes this chapter.'
      ),
      host,
    ],
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Close'
      ),
    ],
  });

  if (!(chapter.content || '').trim()) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Write or draft this chapter before checking it.')
    );
    return;
  }
  if (!model) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Choose a model in Settings before checking continuity.')
    );
    return;
  }
  host.replaceChildren(el('p', { class: 'hint' }, 'Comparing with canon…'));
  api
    .post(`/api/chapters/${chapter.id}/continuity`, {
      model,
      temperature: Number(settings.temperature ?? 0.2),
      top_p: Number(settings.top_p ?? 0.9),
      num_predict: Number(settings.num_predict ?? 700),
      context_window: Number(settings.context_window ?? 4096),
    })
    .then((result) => {
      const findings = result.findings || [];
      host.replaceChildren(
        el(
          'p',
          { class: 'hint' },
          `Checked against ${count(result.canon_count)} canon record${
            result.canon_count === 1 ? '' : 's'
          }.`
        ),
        findings.length
          ? el(
              'div',
              { class: 'review-list' },
              findings.map((finding) =>
                el(
                  'div',
                  { class: 'review-finding' },
                  el(
                    'div',
                    { class: 'review-finding-head' },
                    el(
                      'span',
                      { class: `chip severity-${finding.severity}` },
                      finding.severity
                    ),
                    el('span', { class: 'chip' }, finding.kind)
                  ),
                  el('p', { class: 'review-quote' }, `“${finding.quote}”`),
                  el('p', { class: 'continuity-source' }, `Against · ${finding.source}`),
                  el(
                    'p',
                    { class: 'hint' },
                    `Provenance · ${finding.source_kind || 'canon record'}${
                      finding.source_chapter_position
                        ? ` · chapter ${finding.source_chapter_position}${
                            finding.source_chapter_title
                              ? ` “${finding.source_chapter_title}”`
                              : ''
                          }`
                        : ''
                    }`
                  ),
                  el('p', {}, finding.explanation),
                  finding.suggestion
                    ? el('p', { class: 'review-replacement' }, finding.suggestion)
                    : null
                )
              )
            )
          : el('p', {}, 'No contradictions found in the recorded canon.')
      );
    })
    .catch((error) => {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
}

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
    [2048, 4096, 8192, 16384].map((value) => ({ value: String(value), label: `${value} tokens` })),
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
  const approved = chapter.status === 'approved';
  const used = record.context?.chapters || [];
  const usedEvents = record.context?.events || [];
  const output = textarea({ value: record.output, rows: 16, class: 'textarea chapter-text' });
  const append = input({ type: 'checkbox' });
  append.checked = Boolean(existing);
  const reviewHost = el('div', { class: 'review-findings' });
  const review = el(
    'button',
    { class: 'btn btn-ghost btn-sm', type: 'button', onClick: () => requestReview() },
    icon('search'),
    'Review draft'
  );

  async function requestReview() {
    const text = output.value.trim();
    if (!text) {
      toast('There is no draft to review.', 'error');
      return;
    }
    const state = ctx.state;
    const models = (state.ollama?.models || []).map((model) => model.name);
    const saved = state.settings.generation;
    const model = models.includes(saved.model) ? saved.model : models[0] || '';
    if (!model) {
      toast('Choose a model in Settings first.', 'error');
      return;
    }
    review.disabled = true;
    review.replaceChildren(icon('refresh'), 'Reviewing…');
    try {
      const result = await api.post(`/api/chapters/${chapter.id}/review`, {
        model,
        draft: text,
        temperature: 0.2,
        top_p: Number(saved.top_p),
        num_predict: Number(saved.num_predict),
        context_window: Number(saved.context_window),
      });
      renderReview(reviewHost, result, (finding) => {
        if (!finding.replacement) return;
        if (!output.value.includes(finding.quote)) {
          toast('That passage is no longer in the draft.', 'error');
          return;
        }
        output.value = output.value.replace(finding.quote, finding.replacement);
        toast('Revision applied to the draft.', 'success');
      });
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      review.disabled = false;
      review.replaceChildren(icon('search'), 'Review draft');
    }
  }

  const insert = el(
    'button',
    {
      class: 'btn btn-primary',
      type: 'button',
      disabled: approved,
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
        el(
          'div',
          { style: { display: 'flex', gap: '10px', alignItems: 'center' } },
          el('span', { class: 'hint' }, 'Edit before inserting if needed.'),
          review
        )
      ),
      used.length || usedEvents.length ? contextUsed(used, usedEvents) : null,
      output,
      reviewHost,
      approved
        ? el(
            'p',
            { class: 'revision-warning' },
            'This chapter is approved. Reopen it before inserting an AI draft.'
          )
        : null,
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

function renderReview(host, result, onApply) {
  const findings = result.findings || [];
  const cards = findings.map((finding) =>
    el(
      'div',
      { class: 'review-finding' },
      el(
        'div',
        { class: 'review-finding-head' },
        el('span', { class: 'chip accent' }, finding.kind),
        el('strong', {}, finding.issue || 'Finding')
      ),
      el('blockquote', { class: 'review-quote' }, finding.quote),
      finding.replacement
        ? el('p', { class: 'review-replacement' }, finding.replacement)
        : el('p', { class: 'hint' }, 'No automatic replacement; this is your call.'),
      finding.reason ? el('p', { class: 'hint' }, finding.reason) : null,
      finding.replacement
        ? el(
            'button',
            { class: 'btn btn-sm', type: 'button', onClick: () => onApply(finding) },
            'Apply to draft'
          )
        : null
    )
  );
  host.replaceChildren(
    el('p', { class: 'hint' }, `Reviewed ${count(result.reviewed_chars)} characters.`),
    result.overall ? el('p', {}, result.overall) : null,
    findings.length
      ? el('div', { class: 'review-list' }, cards)
      : el('p', { class: 'hint' }, 'No concrete problems found in this draft.')
  );
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
