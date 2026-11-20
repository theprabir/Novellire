import { api } from '../api.js';
import { count, el, emptyState, icon, openModal, toast } from '../ui.js';

export function renderStyle(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Style'),
        el(
          'div',
          { class: 'sub' },
          'How the manuscript actually reads, and where a chapter departs from your Style Guide. Measurements are counted locally; only a deviation check calls the model, and it changes nothing.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el(
          'a',
          { class: 'btn btn-sm', href: '#/workspace/docs/style_guide' },
          icon('feather'),
          'Style Guide'
        )
      )
    )
  );

  if (!state.activeProjectId || !state.tree) {
    wrap.append(
      emptyState({
        iconName: 'feather',
        title: 'No project selected',
        body: 'Open a project to measure its prose against its style guide.',
        action: el('a', { class: 'btn btn-primary', href: '#/home' }, 'Go home'),
      })
    );
    return wrap;
  }

  const body = el(
    'div',
    {},
    el('p', { class: 'hint' }, 'Measuring the manuscript…')
  );
  wrap.append(body);

  api
    .get(`/api/projects/${state.activeProjectId}/style`)
    .then((profile) => body.replaceChildren(...profileSections(profile, ctx)))
    .catch((error) => {
      toast(error.message, 'error');
      body.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
  return wrap;
}

function profileSections(profile, ctx) {
  const counts = profile.counts || {};
  return [
    el(
      'div',
      { class: 'scope-grid' },
      statCard('Chapters measured', counts.chapters || 0),
      statCard('Words', counts.words || 0),
      statCard('Avg sentence', `${profile.average_sentence_words || 0} words`),
      statCard('Paragraphs with dialogue', `${profile.dialogue_share || 0}%`)
    ),
    el(
      'div',
      { class: 'scope-grid' },
      statCard('Sentences', counts.sentences || 0),
      statCard('Long sentences', counts.long_sentences || 0),
      statCard('Guide rules', counts.rules || 0),
      statCard('Paragraphs', counts.paragraphs || 0)
    ),
    guideSection(profile.guide, ctx),
    chaptersSection(profile, ctx),
  ];
}

function guideSection(guide, ctx) {
  const rules = guide?.rules || [];
  const present = Boolean(guide?.present);
  return el(
    'section',
    { class: 'card form-card' },
    el(
      'div',
      { class: 'review-finding-head' },
      el('h2', { class: 'section-title' }, 'Style Guide rules'),
      present
        ? el(
            'span',
            { class: 'chip' },
            `${count(rules.length)} rule${rules.length === 1 ? '' : 's'}`
          )
        : el('span', { class: 'chip accent' }, 'No guide yet')
    ),
    present
      ? el(
          'p',
          { class: 'hint' },
          'Each paragraph of the guide is numbered, so a deviation can cite your own words instead of an invented rule.'
        )
      : el(
          'p',
          { class: 'hint' },
          'Write the Style Guide in Workspace first. Without it there is no standard to measure deviations against.'
        ),
    present
      ? el(
          'div',
          { class: 'ledger-list' },
          rules.map((rule) =>
            el(
              'div',
              { class: 'ledger-row' },
              el(
                'div',
                { class: 'review-finding-head' },
                el('span', { class: 'chip accent' }, rule.id),
                el('strong', {}, rule.label)
              ),
              rule.guidance && rule.guidance !== rule.label
                ? el('p', { class: 'hint' }, rule.guidance)
                : null
            )
          )
        )
      : el(
          'a',
          { class: 'btn btn-sm', href: '#/workspace/docs/style_guide' },
          icon('feather'),
          'Write the Style Guide'
        ),
    guide?.derived
      ? el(
          'p',
          { class: 'hint' },
          'This guide was learned from the manuscript. Edit it in Workspace to make it your own standard.'
        )
      : null
  );
}

function chaptersSection(profile, ctx) {
  const chapters = profile.chapters || [];
  return el(
    'section',
    { class: 'card form-card' },
    el('h2', { class: 'section-title' }, 'Chapter measurements'),
    el(
      'p',
      { class: 'hint' },
      'Counted from the stored text. A long sentence is over 35 words. A deviation check compares one chapter with the numbered guide rules and reports nothing else.'
    ),
    chapters.length
      ? el(
          'div',
          { class: 'ledger-list' },
          chapters.map((chapter) =>
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
                  `${count(chapter.words)} words · ${
                    chapter.sentences
                  } sentence${chapter.sentences === 1 ? '' : 's'} · ${
                    chapter.average_sentence_words
                  } words per sentence`
                )
              ),
              el(
                'p',
                { class: 'hint' },
                `${chapter.paragraphs} paragraphs · ${
                  chapter.dialogue_paragraphs
                } with dialogue · ${chapter.long_sentences} long · longest sentence ${
                  chapter.longest_sentence_words
                } words${
                  chapter.longest_sentence
                    ? ` (“${chapter.longest_sentence}”)`
                    : ''
                }`
              ),
              el(
                'div',
                { class: 'review-finding-head' },
                el(
                  'button',
                  {
                    class: 'btn btn-sm',
                    type: 'button',
                    title: 'Compare this chapter with the numbered Style Guide rules',
                    onClick: () => openDeviationCheck(ctx, chapter),
                  },
                  icon('sparkles'),
                  'Check deviations'
                )
              )
            )
          )
        )
      : el('p', { class: 'hint' }, 'No chapter with text yet.')
  );
}

function openDeviationCheck(ctx, chapter) {
  const settings = ctx.state.settings?.generation || {};
  const model = settings.model || ctx.state.ollama?.models?.[0]?.name || '';
  const host = el('div', { class: 'review-findings' });
  const modal = openModal({
    title: `Style · chapter ${chapter.position}`,
    wide: true,
    body: [
      el(
        'p',
        { class: 'hint' },
        'One read-only inference compares the saved chapter with the numbered guide rules. Every deviation cites a rule the project holds and quotes this chapter; nothing is written or changed.'
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

  if (!model) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Choose a model in Settings first.')
    );
    return;
  }
  host.replaceChildren(el('p', { class: 'hint' }, 'Comparing with the guide…'));
  api
    .post(`/api/chapters/${chapter.id}/style-check`, {
      model,
      temperature: Number(settings.temperature ?? 0.2),
      top_p: Number(settings.top_p ?? 0.9),
      num_predict: Number(settings.num_predict ?? 700),
      context_window: Number(settings.context_window ?? 4096),
    })
    .then((result) => {
      const deviations = result.deviations || [];
      host.replaceChildren(
        el(
          'p',
          { class: 'hint' },
          `Compared with ${count(result.rule_count)} style rule${
            result.rule_count === 1 ? '' : 's'
          }.`
        ),
        deviations.length
          ? el(
              'div',
              { class: 'review-list' },
              deviations.map((deviation) =>
                el(
                  'div',
                  { class: 'review-finding' },
                  el(
                    'div',
                    { class: 'review-finding-head' },
                    el(
                      'span',
                      { class: `chip severity-${deviation.severity}` },
                      deviation.severity
                    ),
                    el('span', { class: 'chip' }, deviation.aspect)
                  ),
                  el('p', { class: 'review-quote' }, `“${deviation.quote}”`),
                  el(
                    'p',
                    { class: 'continuity-source' },
                    `Against · ${deviation.rule_id} — ${deviation.rule}`
                  ),
                  el('p', {}, deviation.explanation),
                  deviation.suggestion
                    ? el(
                        'p',
                        { class: 'review-replacement' },
                        deviation.suggestion
                      )
                    : null
                )
              )
            )
          : el('p', {}, 'No deviations from the guide were found in this chapter.')
      );
    })
    .catch((error) => {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
    });
}

function statCard(label, value) {
  return el(
    'div',
    { class: 'card scope-card' },
    el('div', { class: 'scope-head' }, icon('feather'), el('strong', {}, label)),
    el('p', { class: 'stat-value' }, typeof value === 'number' ? count(value) : value)
  );
}
