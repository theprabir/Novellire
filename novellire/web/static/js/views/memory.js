import { api } from '../api.js';
import {
  confirmDialog,
  count,
  el,
  emptyState,
  field,
  icon,
  input,
  openModal,
  select,
  textarea,
  toast,
} from '../ui.js';

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

  wrap.append(eventsSection(project.id), form, bulkSummaryCard(ctx, pending), results);
  return wrap;
}

function eventsSection(projectId) {
  const list = el(
    'div',
    { class: 'memory-events-list' },
    el('p', { class: 'hint' }, 'Loading episodic memory…')
  );
  const filter = select(
    [{ value: '', label: 'All characters' }],
    { value: '', disabled: true, 'aria-label': 'Filter events by character' }
  );
  const section = el(
    'section',
    { class: 'memory-events' },
    el(
      'div',
      { class: 'section-head' },
      el(
        'div',
        { class: 'memory-events-title' },
        el('h2', {}, 'Episodic memory'),
        el('span', { class: 'hint' }, 'Extracted events with chapter provenance')
      ),
      filter
    ),
    list
  );

  let events = [];
  let characters = [];

  const render = () => {
    const selected = filter.value ? Number(filter.value) : null;
    const visible = selected
      ? events.filter((event) =>
          (event.character_ids || []).includes(selected)
        )
      : events;
    if (!events.length) {
      list.replaceChildren(
        el(
          'div',
          { class: 'card card-pad' },
          el(
            'p',
            { class: 'hint' },
            'No episodic events yet. Open a chapter and choose Extract events to build this memory.'
          )
        )
      );
      return;
    }
    const characterName = characters.find(
      (character) => character.id === selected
    )?.name;
    list.replaceChildren(
      visible.length
        ? el(
            'div',
            { class: 'event-list' },
            ...visible.map((event) =>
              eventCard(event, characters, refresh)
            )
          )
        : el(
            'div',
            { class: 'card card-pad' },
            el(
              'p',
              { class: 'hint' },
              `No events are linked to ${characterName || 'that character'}.`
            )
          ),
      el(
        'p',
        { class: 'hint' },
        selected
          ? `${count(visible.length)} of ${count(events.length)} events linked to ${characterName}.`
          : `${count(events.length)} event${events.length === 1 ? '' : 's'} stored.`
      )
    );
  };

  async function refresh() {
    try {
      events = await api.get(`/api/projects/${projectId}/events`);
      if (!characters.length) {
        characters = await api
          .get(`/api/projects/${projectId}/characters`)
          .catch(() => []);
      }
      const options = [
        { value: '', label: 'All characters' },
        ...characters.map((character) => ({
          value: character.id,
          label: character.name,
        })),
      ];
      const selected = filter.value;
      filter.replaceChildren(
        ...options.map((option) => {
          const node = el('option', { value: option.value }, option.label);
          if (String(option.value) === String(selected)) node.selected = true;
          return node;
        })
      );
      filter.disabled = characters.length === 0;
      render();
    } catch (error) {
      list.replaceChildren(el('p', { class: 'hint' }, error.message));
    }
  }

  filter.addEventListener('change', render);
  refresh();
  return section;
}

function eventCard(event, characters, refresh) {
  const tags = [
    ['Characters', event.characters],
    ['Locations', event.locations],
    ['Objects', event.objects],
  ]
    .filter(([, values]) => values?.length)
    .map(([label, values]) =>
      el('span', { class: 'chip' }, `${label}: ${values.join(', ')}`)
    );
  const linked = (event.character_ids || [])
    .map((id) => characters.find((character) => character.id === id)?.name)
    .filter(Boolean);
  if (linked.length) {
    tags.push(
      el('span', { class: 'chip accent' }, `Linked: ${linked.join(', ')}`)
    );
  }

  const actions = el(
    'div',
    { class: 'event-actions' },
    el(
      'button',
      {
        class: 'btn btn-ghost btn-sm',
        type: 'button',
        onClick: () => openEventEditor(event, refresh),
      },
      icon('pencil'),
      'Edit'
    ),
    el(
      'button',
      {
        class: 'btn btn-ghost btn-sm',
        type: 'button',
        onClick: () => deleteEvent(event, refresh),
      },
      icon('trash'),
      'Delete'
    )
  );

  return el(
    'article',
    { class: 'event-card' },
    el(
      'div',
      { class: 'event-head' },
      el(
        'span',
        { class: 'chip accent' },
        `Chapter ${event.chapter_position} — ${event.chapter_title}`
      ),
      event.model ? el('span', { class: 'hint' }, event.model) : null,
      actions
    ),
    el('p', { class: 'event-summary' }, event.summary),
    tags.length ? el('div', { class: 'event-tags' }, ...tags) : null,
    event.threads?.length
      ? el(
          'div',
          { class: 'event-threads' },
          el('strong', {}, 'Unresolved'),
          el(
            'ul',
            {},
            ...event.threads.map((thread) => el('li', {}, thread))
          )
        )
      : null
  );
}

function splitList(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function openEventEditor(event, refresh) {
  const summary = textarea({ rows: 3, value: event.summary });
  const characters = input({
    value: (event.characters || []).join(', '),
  });
  const locations = input({ value: (event.locations || []).join(', ') });
  const objects = input({ value: (event.objects || []).join(', ') });
  const threads = input({ value: (event.threads || []).join(', ') });

  const save = el(
    'button',
    { class: 'btn btn-primary', type: 'button' },
    'Save event'
  );
  const modal = openModal({
    title: 'Edit event',
    wide: true,
    body: [
      field('Summary', summary),
      field(
        'Characters',
        characters,
        'Comma-separated names or aliases. Links update when you save.'
      ),
      field('Locations', locations, 'Comma-separated.'),
      field('Objects', objects, 'Comma-separated.'),
      field('Unresolved threads', threads, 'Comma-separated questions.'),
    ],
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Cancel'
      ),
      save,
    ],
  });

  save.addEventListener('click', async () => {
    if (!summary.value.trim()) {
      toast('An event needs a summary.', 'error');
      summary.focus();
      return;
    }
    modal.setBusy(true);
    try {
      await api.patch(`/api/events/${event.id}`, {
        summary: summary.value.trim(),
        characters: splitList(characters.value),
        locations: splitList(locations.value),
        objects: splitList(objects.value),
        threads: splitList(threads.value),
      });
      modal.close();
      toast('Event updated.', 'success');
      await refresh();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      modal.setBusy(false);
    }
  });
}

function deleteEvent(event, refresh) {
  confirmDialog({
    title: 'Delete event',
    message: `Remove “${event.summary}” from episodic memory? This cannot be undone.`,
    confirmLabel: 'Delete event',
    onConfirm: async () => {
      try {
        await api.del(`/api/events/${event.id}`);
        toast('Event deleted.', 'success');
        await refresh();
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
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
