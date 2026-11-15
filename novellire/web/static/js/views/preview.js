import {
  count,
  el,
  emptyState,
  icon,
  proseNodes,
  statusChip,
} from '../ui.js';

const FONT_LABELS = { garamond: 'Garamond', georgia: 'Georgia', palatino: 'Palatino' };

export function renderPreview(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  if (!state.activeProjectId || !state.manuscript) {
    wrap.append(
      el('div', { class: 'page-head' }, el('div', {}, el('h1', {}, 'Preview'))),
      emptyState({
        iconName: 'book',
        title: 'Nothing to read yet',
        body: 'Select a project with chapters, or add a chapter in the workspace. The reader renders scene prose as a typeset manuscript.',
        action: el('a', { class: 'btn btn-primary', href: '#/projects' }, 'Go to projects'),
      })
    );
    return wrap;
  }

  const chapters = state.manuscript.chapters;
  if (!chapters.length) {
    wrap.append(
      el('div', { class: 'page-head' }, el('div', {}, el('h1', {}, 'Preview'))),
      emptyState({
        iconName: 'book',
        title: 'This project has no chapters',
        body: 'Create a chapter and a scene in the workspace, then the manuscript appears here.',
        action: el('a', { class: 'btn btn-primary', href: '#/workspace/chapters' }, 'Open chapter map'),
      })
    );
    return wrap;
  }

  const selected =
    chapters.find((chapter) => chapter.id === state.previewChapterId) || chapters[0];
  state.previewChapterId = selected.id;
  const index = chapters.findIndex((chapter) => chapter.id === selected.id);

  const appearance = state.settings.appearance;
  const sizeLabel = el('span', { class: 'size-value' }, `${appearance.reading_font_size}px`);

  const changeSize = async (delta) => {
    const current = ctx.state.settings.appearance.reading_font_size;
    const next = Math.min(26, Math.max(15, current + delta));
    if (next === current) return;
    await ctx.saveAppearance({ reading_font_size: next }, { rerender: false });
    sizeLabel.textContent = `${next}px`;
  };

  const toolbar = el(
    'div',
    { class: 'reader-toolbar' },
    el(
      'div',
      { class: 'group' },
      el(
        'button',
        {
          class: 'btn btn-sm',
          type: 'button',
          disabled: index <= 0,
          onClick: () => goto(ctx, chapters[index - 1]?.id),
        },
        icon('chevron-left'),
        'Previous'
      ),
      el(
        'button',
        {
          class: 'btn btn-sm',
          type: 'button',
          disabled: index >= chapters.length - 1,
          onClick: () => goto(ctx, chapters[index + 1]?.id),
        },
        'Next',
        icon('chevron-right')
      ),
      el('span', { class: 'hint' }, `Chapter ${index + 1} of ${chapters.length}`)
    ),
    el(
      'div',
      { class: 'group' },
      el('span', { class: 'chip' }, `${FONT_LABELS[appearance.reading_font] || 'Garamond'}`),
      el(
        'div',
        { class: 'reader-controls' },
        el('button', { class: 'icon-btn', type: 'button', title: 'Smaller reading text', 'aria-label': 'Smaller reading text', onClick: () => changeSize(-1) }, 'A−'),
        sizeLabel,
        el('button', { class: 'icon-btn', type: 'button', title: 'Larger reading text', 'aria-label': 'Larger reading text', onClick: () => changeSize(1) }, 'A+')
      ),
      el(
        'a',
        { class: 'btn btn-sm', href: `#/workspace/chapters/${selected.id}` },
        icon('file'),
        'Open in editor'
      )
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'page-head', style: { marginBottom: '16px' } },
      el(
        'div',
        {},
        el('h1', {}, 'Preview'),
        el(
          'div',
          { class: 'sub' },
          `${state.manuscript.project.name} · ${count(chapters.reduce((total, chapter) => total + chapter.word_count, 0))} words across ${chapters.length} chapters`
        )
      ),
      el('div', { class: 'actions' }, statusChip(selected.status, state.meta))
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'preview-layout' },
      chapterNav(ctx, chapters, selected.id),
      el('div', { class: 'reader-stage' }, toolbar, readerSurface(selected))
    )
  );

  return wrap;
}

function chapterNav(ctx, chapters, activeId) {
  const nav = el('aside', { class: 'chapter-nav', 'aria-label': 'Chapters' }, el('div', { class: 'nav-title' }, 'Chapters'));
  for (const chapter of chapters) {
    nav.append(
      el(
        'button',
        {
          class: 'chapter-link',
          type: 'button',
          'aria-current': chapter.id === activeId ? 'true' : undefined,
          onClick: () => goto(ctx, chapter.id),
        },
        el('small', {}, `Chapter ${chapter.position}`),
        el('span', {}, chapter.title),
        el('small', {}, `${count(chapter.word_count)} words`)
      )
    );
  }
  return nav;
}

function readerSurface(chapter) {
  const scenes = chapter.scenes || [];
  const sections = scenes.map((scene) =>
    el(
      'section',
      { class: 'scene' },
      scene.title ? el('div', { class: 'scene-title' }, scene.title) : null,
      proseNodes(scene.content)
    )
  );

  return el(
    'article',
    { class: 'reader', 'aria-label': `Chapter ${chapter.position}: ${chapter.title}` },
    el('div', { class: 'chapter-eyebrow' }, `Chapter ${chapter.position}`),
    el('h1', {}, chapter.title),
    chapter.summary ? el('p', { class: 'chapter-summary' }, chapter.summary) : null,
    el('div', { class: 'rule' }),
    scenes.length
      ? sections
      : el('p', { class: 'reader-empty' }, 'This chapter has no scenes yet.'),
    el(
      'div',
      { class: 'colophon' },
      el('span', {}, `${count(chapter.word_count)} words`),
      el('span', {}, chapter.part || 'Manuscript')
    )
  );
}

function goto(ctx, chapterId) {
  if (!chapterId) return;
  window.location.hash = `#/preview/${chapterId}`;
}
