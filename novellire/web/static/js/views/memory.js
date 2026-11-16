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
  const pending = chapters.filter(
    (chapter) => chapter.content?.trim() && !chapter.summary?.trim()
  ).length;

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

  wrap.append(form, bulkSummaryCard(ctx, pending), results);
  return wrap;
}

function bulkSummaryCard(ctx, pending) {
  const status = el(
    'p',
    { class: 'hint bulk-status' },
    pending
      ? `${count(pending)} chapter${pending === 1 ? '' : 's'} without a summary. The model runs one chapter at a time.`
      : 'Every chapter with text already has a summary.'
  );
  const list = el('div', { class: 'bulk-list' });
  const button = el(
    'button',
    { class: 'btn', type: 'button' },
    icon('sparkles'),
    'Summarise all chapters'
  );
  button.disabled = pending === 0;
  button.addEventListener('click', () =>
    summariseProject(ctx, button, status, list)
  );

  return el(
    'div',
    { class: 'card card-pad bulk-summary' },
    el(
      'div',
      { class: 'bulk-summary-head' },
      el(
        'div',
        {},
        el('h2', {}, 'Bulk summaries'),
        status
      ),
      button
    ),
    list
  );
}

async function summariseProject(ctx, button, status, list) {
  const state = ctx.state;
  const model =
    state.settings?.generation?.model || state.ollama?.models?.[0]?.name || '';
  const counts = { summarised: 0, skipped: 0, empty: 0, failed: 0 };
  let total = 0;

  button.disabled = true;
  button.replaceChildren(icon('refresh'), 'Summarising…');
  list.replaceChildren();
  status.textContent = 'Starting…';

  try {
    await api.stream(
      `/api/projects/${state.activeProjectId}/summaries`,
      { model },
      (event) => {
        if (event.type === 'start') {
          total = event.total;
          status.textContent = `Running 0 of ${count(total)} chapters…`;
        } else if (event.type === 'step') {
          counts[event.status] = (counts[event.status] || 0) + 1;
          list.append(summaryStepRow(event));
          status.textContent = `Running ${count(event.processed)} of ${count(total)} chapters…`;
        } else if (event.type === 'done') {
          status.textContent = summaryTotals(event);
        }
      }
    );
    toast(
      `Bulk summary finished: ${count(counts.summarised)} generated, ${count(
        counts.skipped
      )} already had one.`,
      counts.failed ? 'error' : 'success'
    );
  } catch (error) {
    status.textContent = 'Bulk summary stopped. Chapters completed so far are saved.';
    toast(error.message, 'error');
  } finally {
    const complete =
      total > 0 &&
      counts.failed === 0 &&
      counts.summarised + counts.skipped + counts.empty === total;
    button.disabled = complete;
    button.replaceChildren(icon('sparkles'), 'Summarise all chapters');
  }
}

const STEP_LABELS = {
  summarised: 'Summarised',
  skipped: 'Already summarised',
  empty: 'No chapter text',
  failed: 'Failed',
};

function summaryStepRow(event) {
  const label = STEP_LABELS[event.status] || event.status;
  return el(
    'div',
    { class: `bulk-row ${event.status}` },
    el(
      'div',
      { class: 'bulk-row-main' },
      el('span', { class: 'bulk-row-position' }, count(event.position)),
      el('strong', {}, event.title),
      el('span', { class: `chip ${event.status === 'summarised' ? 'accent' : ''}`.trim() }, label)
    ),
    event.detail ? el('p', { class: 'hint' }, event.detail) : null
  );
}

function summaryTotals(event) {
  const parts = [];
  if (event.summarised) parts.push(`${count(event.summarised)} generated`);
  if (event.skipped) parts.push(`${count(event.skipped)} already had one`);
  if (event.empty) parts.push(`${count(event.empty)} without text`);
  if (event.failed) parts.push(`${count(event.failed)} failed`);
  return parts.length ? `Finished: ${parts.join(', ')}.` : 'Nothing to summarise.';
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
