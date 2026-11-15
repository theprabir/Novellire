import { el, emptyState, icon, textarea } from '../ui.js';

export function renderChat(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });
  const project = state.tree?.project;

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Chat'),
        el(
          'div',
          { class: 'sub' },
          'A project-scoped conversation surface. Designed now so retrieval-backed discussion can drop in without a redesign.'
        )
      ),
      el('div', { class: 'actions' }, el('span', { class: 'chip soon' }, 'Phase 4'))
    )
  );

  const history = el(
    'aside',
    { class: 'chat-history' },
    el('div', { class: 'history-title' }, 'Conversations'),
    emptyState({
      iconName: 'clock',
      title: 'No conversations yet',
      body: 'History will list every thread for the active project.',
    }),
    el('button', { class: 'btn btn-block', type: 'button', disabled: true }, icon('plus'), 'New conversation')
  );

  const stream = el(
    'div',
    { class: 'chat-stream' },
    el(
      'div',
      { class: 'chat-bubble' },
      el('span', { class: 'avatar' }, icon('feather', 'icon sm')),
      el(
        'div',
        { class: 'bubble' },
        'This is the planned chat scope. When narrative memory and retrieval land, questions here will be answered from the active project’s story bible, chapters, and character state — not from the model’s guesswork.'
      )
    )
  );

  const composer = el(
    'div',
    { class: 'chat-composer' },
    el(
      'div',
      { class: 'composer-row' },
      textarea({
        placeholder: 'Ask about canon, characters, or what happens next…',
        rows: 2,
        disabled: true,
      }),
      el('button', { class: 'btn btn-primary', type: 'button', disabled: true }, icon('sparkles'), 'Send')
    ),
    el(
      'div',
      { class: 'composer-note' },
      icon('alert', 'icon sm'),
      'Not connected yet — chat is a designed scope for Phase 4.'
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'chat-shell' },
      history,
      el(
        'div',
        { class: 'chat-main' },
        el(
          'div',
          { class: 'chat-head' },
          el('strong', {}, project ? `${project.name} — new conversation` : 'No project selected'),
          el('span', { class: 'chip' }, 'Project scoped')
        ),
        stream,
        composer
      )
    )
  );

  return wrap;
}

const SCOPES = {
  continuity: {
    title: 'Continuity',
    icon: 'shield',
    phase: 'Phase 5',
    subtitle:
      'A review surface for contradictions the harness finds between generated prose and established canon.',
    cards: [
      { title: 'Timeline conflicts', body: 'Events that cannot occur in the recorded order.' },
      { title: 'Character knowledge', body: 'A character acting on information they never learned.' },
      { title: 'Canon conflicts', body: 'Prose contradicting an approved story bible entry.' },
      { title: 'Unresolved threads', body: 'Planted mysteries and promises still waiting to pay off.' },
    ],
  },
};

export function renderScope(ctx, key) {
  const scope = SCOPES[key] || SCOPES.continuity;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, scope.title),
        el('div', { class: 'sub' }, scope.subtitle)
      ),
      el('div', { class: 'actions' }, el('span', { class: 'chip soon' }, scope.phase))
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'card card-pad', style: { marginBottom: '18px', display: 'flex', gap: '12px', alignItems: 'flex-start' } },
      icon('alert'),
      el(
        'div',
        {},
        el('strong', { style: { fontSize: 'var(--fs-sm)' } }, 'This surface is a layout scope'),
        el(
          'p',
          { class: 'hint', style: { marginTop: '4px' } },
          'The panels, filters, and detail views are reserved so the backend feature can be connected without redesigning the interface. No data is displayed yet.'
        )
      )
    )
  );

  const grid = el('div', { class: 'scope-grid' });
  for (const card of scope.cards) {
    grid.append(
      el(
        'div',
        { class: 'card scope-card' },
        el('div', { class: 'scope-head' }, icon(scope.icon), el('strong', {}, card.title)),
        el('p', { class: 'hint' }, card.body),
        el(
          'div',
          { class: 'lines', 'aria-hidden': 'true' },
          el('div', { class: 'skeleton' }),
          el('div', { class: 'skeleton' }),
          el('div', { class: 'skeleton' })
        ),
        el('div', { class: 'foot' }, icon('clock', 'icon sm'), `Wired in ${scope.phase}`)
      )
    );
  }

  const tree = ctx.state.tree;
  if (tree) {
    wrap.append(
      el(
        'p',
        { class: 'hint', style: { marginTop: '16px' } },
        `Project “${tree.project.name}” already has ${tree.stats.chapters} chapters and ${tree.stats.words.toLocaleString()} words ready for this surface to read.`
      )
    );
  }

  wrap.append(grid);
  return wrap;
}
