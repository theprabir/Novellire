import { api } from '../api.js';
import { count, el, emptyState, icon, input, toast } from '../ui.js';

export function renderMemory(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Memory'),
        el(
          'div',
          { class: 'sub' },
          'Search chapter prose, stored summaries, and the four project documents. The index lives in this project’s SQLite database.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el('a', { class: 'btn btn-sm', href: '#/workspace' }, icon('layers'), 'Workspace')
      )
    )
  );

  if (!state.activeProjectId || !state.tree) {
    wrap.append(
      emptyState({
        iconName: 'database',
        title: 'No project selected',
        body: 'Open a project to search its chapters, summaries, and documents.',
        action: el('a', { class: 'btn btn-primary', href: '#/home' }, 'Go home'),
      })
    );
    return wrap;
  }

  const project = state.tree.project;
  const chapters = state.manuscript?.chapters || [];
  const summarised = chapters.filter((chapter) => chapter.summary?.trim()).length;

  const query = input({
    type: 'search',
    placeholder: 'Search names, places, phrases…',
    autocomplete: 'off',
  });
  const submit = el(
    'button',
    { class: 'btn btn-primary', type: 'submit' },
    icon('search'),
    'Search'
  );
  const results = el(
    'div',
    { class: 'memory-results' },
    el(
      'div',
      { class: 'card card-pad memory-intro' },
      el(
        'p',
        { class: 'hint' },
        `${count(chapters.length)} chapter${chapters.length === 1 ? '' : 's'} · ${count(
          summarised
        )} with a stored summary. Search is lexical, so exact words and names work best.`
      )
    )
  );

  const form = el(
    'form',
    { class: 'search-bar' },
    query,
    submit
  );
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = query.value.trim();
    if (!text) {
      toast('Enter a word or phrase to search.', 'error');
      return;
    }
    submit.disabled = true;
    submit.replaceChildren(icon('refresh'), 'Searching…');
    try {
      const payload = await api.get(
        `/api/projects/${project.id}/search?q=${encodeURIComponent(text)}&limit=25`
      );
      results.replaceChildren(renderResults(payload.results, text));
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      submit.disabled = false;
      submit.replaceChildren(icon('search'), 'Search');
    }
  });

  wrap.append(form, results);
  return wrap;
}

function renderResults(hits, query) {
  if (!hits.length) {
    return el(
      'div',
      { class: 'empty' },
      icon('search', 'icon'),
      el('h3', {}, 'No matches'),
      el('p', {}, `Nothing in this project matches “${query}”. Try a character, place, or shorter phrase.`)
    );
  }

  const list = el('div', { class: 'memory-list' });
  for (const hit of hits) {
    list.append(hitCard(hit));
  }
  return el(
    'div',
    {},
    el(
      'div',
      { class: 'section-head' },
      el('h2', {}, 'Results'),
      el('span', { class: 'hint' }, `${count(hits.length)} match${hits.length === 1 ? '' : 'es'}`)
    ),
    list
  );
}

function hitCard(hit) {
  const isChapter = hit.kind === 'chapter';
  const href = isChapter
    ? `#/workspace/chapters/${hit.source_id}`
    : `#/workspace/docs/${hit.kind}`;
  const label = isChapter ? 'Chapter' : 'Document';

  return el(
    'a',
    { class: 'memory-hit', href },
    el(
      'div',
      { class: 'memory-hit-head' },
      el('span', { class: `chip ${isChapter ? 'accent' : ''}`.trim() }, label),
      el('strong', {}, hit.title),
      icon('arrow-right', 'icon sm')
    ),
    el('p', { class: 'memory-excerpt' }, hit.excerpt)
  );
}
