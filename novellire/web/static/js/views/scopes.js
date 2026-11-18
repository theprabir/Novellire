import { el, icon } from '../ui.js';

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
      {
        class: 'card card-pad',
        style: { marginBottom: '18px', display: 'flex', gap: '12px', alignItems: 'flex-start' },
      },
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
