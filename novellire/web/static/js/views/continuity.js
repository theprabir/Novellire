import { api } from '../api.js';
import {
  count,
  el,
  emptyState,
  field,
  icon,
  openModal,
  select,
  textarea,
  toast,
} from '../ui.js';

const FIELD_LABELS = {
  location: 'Location',
  status: 'Status',
  goals: 'Goals',
  knowledge: 'Knowledge',
};

export function renderContinuity(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Continuity'),
        el(
          'div',
          { class: 'sub' },
          'The recorded canon: chapter order, character state over time, and unresolved threads. Every row keeps its chapter provenance; no model is involved.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el(
          'a',
          { class: 'btn btn-sm', href: '#/workspace' },
          icon('layers'),
          'Check a chapter'
        )
      )
    )
  );

  if (!state.activeProjectId || !state.tree) {
    wrap.append(
      emptyState({
        iconName: 'shield',
        title: 'No project selected',
        body: 'Open a project to inspect its recorded timeline and canon.',
        action: el('a', { class: 'btn btn-primary', href: '#/home' }, 'Go home'),
      })
    );
    return wrap;
  }

  const body = el('div', { class: 'review-findings' }, el('p', { class: 'hint' }, 'Reading recorded canon…'));
  wrap.append(body);

  api
    .get(`/api/projects/${state.activeProjectId}/continuity`)
    .then((ledger) => body.replaceChildren(...ledgerSections(ledger, ctx)))
    .catch((error) => {
      toast(error.message, 'error');
      body.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
  return wrap;
}

function ledgerSections(ledger, ctx) {
  const projectId = ctx.state.activeProjectId;
  const counts = ledger.counts || {};
  const sections = [
    el(
      'div',
      { class: 'scope-grid' },
      statCard('Chapters', counts.chapters || 0),
      statCard('Recorded events', counts.events || 0),
      statCard('State snapshots', counts.states || 0),
      statCard('Open threads', counts.open_threads || 0)
    ),
  ];

  const timeline = ledger.timeline || [];
  sections.push(
    el(
      'section',
      { class: 'card form-card' },
      el('h2', { class: 'section-title' }, 'Recorded timeline'),
      timeline.length
        ? el(
            'div',
            { class: 'ledger-list' },
            timeline.map((chapter) =>
              el(
                'div',
                { class: 'ledger-row' },
                el(
                  'div',
                  { class: 'review-finding-head' },
                  el('span', { class: 'chip' }, String(chapter.position).padStart(2, '0')),
                  el('strong', {}, chapter.title || 'Untitled chapter'),
                  el(
                    'span',
                    { class: 'hint' },
                    `${count(chapter.word_count)} words · ${chapter.events.length} event${
                      chapter.events.length === 1 ? '' : 's'
                    }`
                  )
                ),
                chapter.events.length
                  ? el(
                      'ul',
                      { class: 'ledger-events' },
                      chapter.events.map((event) =>
                        el(
                          'li',
                          {},
                          event.summary,
                          event.threads?.length
                            ? el(
                                'span',
                                { class: 'hint' },
                                ` · thread: ${event.threads.join('; ')}`
                              )
                            : null
                        )
                      )
                    )
                  : el('p', { class: 'hint' }, 'No events extracted for this chapter.')
              )
            )
          )
        : el('p', { class: 'hint' }, 'No chapters yet.')
    )
  );

  const characters = ledger.characters || [];
  sections.push(
    el(
      'section',
      { class: 'card form-card' },
      el('h2', { class: 'section-title' }, 'Character knowledge over time'),
      characters.length
        ? el(
            'div',
            { class: 'ledger-list' },
            characters.map((character) =>
              el(
                'div',
                { class: 'ledger-row' },
                el('div', { class: 'review-finding-head' }, el('strong', {}, character.name)),
                ...character.snapshots.map((snapshot) =>
                  el(
                    'div',
                    { class: 'ledger-snapshot' },
                    el(
                      'div',
                      { class: 'review-finding-head' },
                      el(
                        'span',
                        { class: 'hint' },
                        `Chapter ${snapshot.chapter_position} “${snapshot.chapter_title}”`
                      ),
                      ...(snapshot.changed || []).map((field) =>
                        el('span', { class: 'chip accent' }, FIELD_LABELS[field] || field)
                      )
                    ),
                    ...Object.entries(FIELD_LABELS)
                      .filter(([field]) => snapshot[field])
                      .map(([field, label]) => el('p', { class: 'hint' }, `${label}: ${snapshot[field]}`))
                  )
                )
              )
            )
          )
        : el(
            'p',
            { class: 'hint' },
            'No character state snapshots yet. Record them in Memory to build this timeline.'
          )
    )
  );

  const threads = ledger.threads || [];
  const timelineRows = ledger.timeline || [];
  sections.push(
    el(
      'section',
      { class: 'card form-card' },
      el('h2', { class: 'section-title' }, 'Plot threads'),
      threads.length
        ? el(
            'div',
            { class: 'ledger-list' },
            threads.map((thread) =>
              el(
                'div',
                { class: 'ledger-row' },
                el(
                  'div',
                  { class: 'review-finding-head' },
                  el(
                    'span',
                    {
                      class:
                        thread.status === 'resolved'
                          ? 'chip severity-low'
                          : 'chip accent',
                    },
                    thread.status || 'open'
                  ),
                  el('strong', {}, thread.thread)
                ),
                el(
                  'p',
                  { class: 'hint' },
                  `Raised or mentioned in ${thread.chapters
                    .map((chapter) => `chapter ${chapter.position}`)
                    .join(', ')} · ${thread.event_count} event${
                    thread.event_count === 1 ? '' : 's'
                  }`
                ),
                thread.status === 'resolved'
                  ? el(
                      'p',
                      { class: 'hint' },
                      `Resolved${
                        thread.resolved_chapter
                          ? ` in chapter ${thread.resolved_chapter.position} “${thread.resolved_chapter.title}”`
                          : ''
                      }${thread.note ? ` · ${thread.note}` : ''}`
                    )
                  : null,
                el(
                  'div',
                  { class: 'review-finding-head' },
                  thread.status === 'resolved'
                    ? el(
                        'button',
                        {
                          class: 'btn btn-sm',
                          type: 'button',
                          onClick: () => reopenThread(ctx, projectId, thread),
                        },
                        'Reopen'
                      )
                    : el(
                        'button',
                        {
                          class: 'btn btn-sm',
                          type: 'button',
                          onClick: () =>
                            resolveThread(ctx, projectId, thread, timelineRows),
                        },
                        'Resolve'
                      )
                )
              )
            )
          )
        : el(
            'p',
            { class: 'hint' },
            'No threads recorded. Extract events for a chapter to collect them.'
          )
    )
  );

  return sections;
}

function resolveThread(ctx, projectId, thread, chapters) {
  const note = textarea({
    rows: 3,
    placeholder: 'How it pays off, if useful later.',
  });
  const chapter = select([
    { value: '', label: 'No chapter' },
    ...chapters.map((row) => ({
      value: row.id,
      label: `${row.position}. ${row.title}`,
    })),
  ]);
  const save = el('button', { class: 'btn btn-primary', type: 'button' }, 'Resolve');
  const modal = openModal({
    title: 'Resolve thread',
    body: [
      el('p', { class: 'review-quote' }, thread.thread),
      field('Resolution note', note, 'Optional. Stored with the thread, not written into prose.'),
      field('Paid off in', chapter, 'Optional chapter provenance.'),
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
    save.disabled = true;
    try {
      await api.put(`/api/projects/${projectId}/threads`, {
        thread: thread.thread,
        status: 'resolved',
        note: note.value,
        chapter_id: chapter.value ? Number(chapter.value) : null,
      });
      modal.close();
      toast('Thread resolved.', 'success');
      await ctx.refresh();
    } catch (error) {
      toast(error.message, 'error');
      save.disabled = false;
    }
  });
}

async function reopenThread(ctx, projectId, thread) {
  try {
    await api.put(`/api/projects/${projectId}/threads`, {
      thread: thread.thread,
      status: 'open',
    });
    toast('Thread reopened.', 'success');
    await ctx.refresh();
  } catch (error) {
    toast(error.message, 'error');
  }
}

function statCard(label, value) {
  return el(
    'div',
    { class: 'card scope-card' },
    el('div', { class: 'scope-head' }, icon('shield'), el('strong', {}, label)),
    el('p', { class: 'stat-value' }, count(value))
  );
}
