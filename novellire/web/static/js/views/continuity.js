import { api } from '../api.js';
import { count, el, emptyState, icon, toast } from '../ui.js';

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
    .then((ledger) => body.replaceChildren(...ledgerSections(ledger)))
    .catch((error) => {
      toast(error.message, 'error');
      body.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
  return wrap;
}

function ledgerSections(ledger) {
  const counts = ledger.counts || {};
  const sections = [
    el(
      'div',
      { class: 'scope-grid' },
      statCard('Chapters', counts.chapters || 0),
      statCard('Recorded events', counts.events || 0),
      statCard('State snapshots', counts.states || 0),
      statCard('Unresolved threads', counts.threads || 0)
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
  sections.push(
    el(
      'section',
      { class: 'card form-card' },
      el('h2', { class: 'section-title' }, 'Unresolved threads'),
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
                  el('span', { class: 'chip accent' }, 'open'),
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
                )
              )
            )
          )
        : el(
            'p',
            { class: 'hint' },
            'No unresolved threads recorded. Extract events for a chapter to collect them.'
          )
    )
  );

  return sections;
}

function statCard(label, value) {
  return el(
    'div',
    { class: 'card scope-card' },
    el('div', { class: 'scope-head' }, icon('shield'), el('strong', {}, label)),
    el('p', { class: 'stat-value' }, count(value))
  );
}
