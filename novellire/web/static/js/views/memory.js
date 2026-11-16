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

  wrap.append(
    eventsSection(project.id, state.meta),
    characterStateSection(project.id),
    form,
    bulkSummaryCard(ctx, pending),
    results
  );
  return wrap;
}

function eventsSection(projectId, meta) {
  const list = el(
    'div',
    { class: 'memory-events-list' },
    el('p', { class: 'hint' }, 'Loading episodic memory…')
  );
  const filter = select(
    [{ value: '', label: 'All characters' }],
    { value: '', disabled: true, 'aria-label': 'Filter events by character' }
  );
  const recorded = el(
    'div',
    { class: 'relationship-list' },
    el('p', { class: 'hint' }, 'Loading recorded relationships…')
  );
  const relationships = el(
    'div',
    { class: 'relationship-list' },
    el('p', { class: 'hint' }, 'Loading derived associations…')
  );
  const recordButton = el(
    'button',
    { class: 'btn btn-sm', type: 'button', disabled: true },
    icon('plus'),
    'Record relationship'
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
    list,
    el(
      'div',
      { class: 'relationship-block' },
      el(
        'div',
        { class: 'relationship-head' },
        el('h3', {}, 'Character relationships'),
        el(
          'span',
          { class: 'hint' },
          'Recorded records are author-controlled; derived associations are not canon'
        ),
        recordButton
      ),
      el(
        'div',
        { class: 'relationship-subhead' },
        el('strong', {}, 'Recorded'),
        el('span', { class: 'hint' }, 'Approved, proposed, and rejected records')
      ),
      recorded,
      el(
        'div',
        { class: 'relationship-subhead' },
        el('strong', {}, 'Derived'),
        el('span', { class: 'hint' }, 'Shared events; not canon')
      ),
      relationships
    )
  );

  let events = [];
  let characters = [];
  let pairs = [];
  let records = [];
  let relationshipError = '';
  let recordError = '';

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
      try {
        pairs = await api.get(`/api/projects/${projectId}/relationships`);
        relationshipError = '';
      } catch (error) {
        pairs = [];
        relationshipError = error.message;
      }
      try {
        records = await api.get(
          `/api/projects/${projectId}/relationship-records`
        );
        recordError = '';
      } catch (error) {
        records = [];
        recordError = error.message;
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
      recordButton.disabled = characters.length < 2;
      render();
      renderRecordedRelationships(
        records,
        recorded,
        recordError,
        meta,
        characters,
        refresh,
        projectId
      );
      renderRelationships(
        pairs,
        relationships,
        relationshipError,
        meta,
        characters,
        refresh,
        projectId
      );
    } catch (error) {
      list.replaceChildren(el('p', { class: 'hint' }, error.message));
      relationships.replaceChildren(
        el('p', { class: 'hint' }, 'Relationships are unavailable.')
      );
      recorded.replaceChildren(
        el('p', { class: 'hint' }, 'Recorded relationships are unavailable.')
      );
    }
  }

  filter.addEventListener('change', render);
  recordButton.addEventListener('click', () => {
    if (characters.length < 2) {
      toast('Add at least two characters before recording a relationship.', 'error');
      return;
    }
    openRelationshipEditor({
      projectId,
      meta,
      characters,
      refresh,
    });
  });
  refresh();
  return section;
}

function characterStateSection(projectId) {
  const host = el(
    'div',
    { class: 'state-list' },
    el('p', { class: 'hint' }, 'Loading character state…')
  );
  const button = el(
    'button',
    { class: 'btn btn-sm', type: 'button', disabled: true },
    icon('plus'),
    'Record state'
  );
  const section = el(
    'section',
    { class: 'memory-state' },
    el(
      'div',
      { class: 'section-head' },
      el(
        'div',
        { class: 'memory-events-title' },
        el('h2', {}, 'Character state'),
        el(
          'span',
          { class: 'hint' },
          'Author-recorded snapshots; the latest chapter is current'
        )
      ),
      button
    ),
    host
  );

  let states = [];
  let characters = [];
  let chapters = [];

  async function refresh() {
    try {
      [states, characters, chapters] = await Promise.all([
        api.get(`/api/projects/${projectId}/character-states`),
        api.get(`/api/projects/${projectId}/characters`),
        api.get(`/api/projects/${projectId}/chapters`),
      ]);
      button.disabled = characters.length === 0 || chapters.length === 0;
      renderCharacterStates(states, host, refresh);
    } catch (error) {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
    }
  }

  button.addEventListener('click', () => {
    if (!characters.length || !chapters.length) {
      toast('Add a character and a chapter before recording state.', 'error');
      return;
    }
    openStateEditor({ projectId, characters, chapters, refresh });
  });

  refresh();
  return section;
}

function renderCharacterStates(states, host, refresh) {
  if (!states.length) {
    host.replaceChildren(
      el(
        'div',
        { class: 'card card-pad' },
        el(
          'p',
          { class: 'hint' },
          'No character state recorded yet. Add a snapshot to track location, status, goals, and knowledge by chapter.'
        )
      )
    );
    return;
  }

  const groups = new Map();
  for (const state of states) {
    if (!groups.has(state.character_id)) groups.set(state.character_id, []);
    groups.get(state.character_id).push(state);
  }

  host.replaceChildren(
    ...[...groups.values()].map((group) => {
      const current = group[0];
      const history = group.slice(1);
      const card = el(
        'article',
        { class: 'state-card' },
        el(
          'div',
          { class: 'state-head' },
          el('strong', {}, current.character_name),
          el(
            'span',
            { class: 'chip accent' },
            `Current · Chapter ${current.chapter_position} — ${current.chapter_title}`
          ),
          stateActions(current, refresh)
        ),
        stateFields(current)
      );
      if (history.length) {
        card.append(
          el(
            'details',
            { class: 'state-history' },
            el(
              'summary',
              {},
              `Earlier snapshots (${history.length})`
            ),
            ...history.map((state) =>
              el(
                'div',
                { class: 'state-history-row' },
                el(
                  'div',
                  { class: 'state-head' },
                  el(
                    'span',
                    { class: 'chip' },
                    `Chapter ${state.chapter_position} — ${state.chapter_title}`
                  ),
                  stateActions(state, refresh)
                ),
                stateFields(state)
              )
            )
          )
        );
      }
      return card;
    })
  );
}

function stateFields(state) {
  const fields = [
    ['Location', state.location],
    ['Status', state.status],
    ['Goals', state.goals],
    ['Knowledge', state.knowledge],
  ].filter(([, value]) => value);
  if (!fields.length) return null;
  return el(
    'dl',
    { class: 'state-fields' },
    ...fields.flatMap(([label, value]) => [
      el('dt', {}, label),
      el('dd', {}, value),
    ])
  );
}

function stateActions(state, refresh) {
  return el(
    'div',
    { class: 'state-actions' },
    el(
      'button',
      {
        class: 'btn btn-ghost btn-sm',
        type: 'button',
        onClick: () =>
          openStateEditor({
            projectId: state.project_id,
            state,
            characters: [],
            chapters: [],
            refresh,
          }),
      },
      icon('pencil'),
      'Edit'
    ),
    el(
      'button',
      {
        class: 'btn btn-ghost btn-sm',
        type: 'button',
        onClick: () => deleteState(state, refresh),
      },
      icon('trash'),
      'Delete'
    )
  );
}

async function deleteState(state, refresh) {
  confirmDialog({
    title: 'Delete state snapshot',
    message: `Remove the Chapter ${state.chapter_position} — ${state.chapter_title} snapshot for ${state.character_name}? Older snapshots remain.`,
    confirmLabel: 'Delete snapshot',
    onConfirm: async () => {
      try {
        await api.del(`/api/character-states/${state.id}`);
        toast('State snapshot deleted.', 'success');
        await refresh();
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
}

function openStateEditor({
  projectId,
  state = null,
  characters,
  chapters,
  refresh,
}) {
  let character = null;
  let chapter = null;
  const body = [];

  if (state) {
    body.push(
      el(
        'p',
        { class: 'hint' },
        `${state.character_name} · Chapter ${state.chapter_position} — ${state.chapter_title}`
      )
    );
  } else {
    character = select(
      characters.map((item) => ({ value: item.id, label: item.name })),
      { value: characters[0]?.id }
    );
    const latestChapter = [...chapters].sort(
      (a, b) => b.position - a.position
    )[0];
    chapter = select(
      chapters.map((item) => ({
        value: item.id,
        label: `Chapter ${item.position} — ${item.title}`,
      })),
      { value: latestChapter?.id }
    );
    body.push(field('Character', character), field('As of chapter', chapter));
  }

  const location = input({ value: state?.location || '' });
  const status = textarea({ rows: 2, value: state?.status || '' });
  const goals = textarea({ rows: 2, value: state?.goals || '' });
  const knowledge = textarea({ rows: 2, value: state?.knowledge || '' });
  body.push(
    field('Location', location),
    field('Status', status, 'Physical, emotional, or situational condition.'),
    field('Goals', goals),
    field('Knowledge', knowledge, 'What this character knows or believes at this point.')
  );

  const save = el(
    'button',
    { class: 'btn btn-primary', type: 'button' },
    state ? 'Save snapshot' : 'Record snapshot'
  );
  const modal = openModal({
    title: state ? 'Edit state snapshot' : 'Record character state',
    wide: true,
    body,
    footer: [
      el(
        'button',
        {
          class: 'btn btn-ghost',
          type: 'button',
          onClick: () => modal.close(),
        },
        'Cancel'
      ),
      save,
    ],
  });

  save.addEventListener('click', async () => {
    const fields = {
      location: location.value.trim(),
      status: status.value.trim(),
      goals: goals.value.trim(),
      knowledge: knowledge.value.trim(),
    };
    if (!Object.values(fields).some(Boolean)) {
      toast('Record at least one state detail.', 'error');
      return;
    }
    modal.setBusy(true);
    try {
      if (state) {
        await api.patch(`/api/character-states/${state.id}`, fields);
        toast('State snapshot updated.', 'success');
      } else {
        await api.post(`/api/projects/${projectId}/character-states`, {
          character_id: Number(character.value),
          chapter_id: Number(chapter.value),
          ...fields,
        });
        toast('State snapshot recorded.', 'success');
      }
      modal.close();
      await refresh();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      modal.setBusy(false);
    }
  });
}

const RELATIONSHIP_STATUS_LABELS = {
  proposed: 'Proposed',
  approved: 'Approved',
  rejected: 'Rejected',
};

function relationshipTypeLabel(meta, key) {
  return (
    (meta?.relationship_types || []).find((item) => item.key === key)?.label ||
    key
  );
}

function relationshipTypeOptions(meta) {
  const options = meta?.relationship_types || [];
  return options.length ? options : [{ key: 'other', label: 'Other' }];
}

function renderRecordedRelationships(
  records,
  host,
  error,
  meta,
  characters,
  refresh,
  projectId
) {
  if (error) {
    host.replaceChildren(el('p', { class: 'hint' }, error));
    return;
  }
  if (!records.length) {
    host.replaceChildren(
      el(
        'div',
        { class: 'card card-pad' },
        el(
          'p',
          { class: 'hint' },
          'No recorded relationships yet. Record one from a derived association or use Record relationship.'
        )
      )
    );
    return;
  }
  host.replaceChildren(
    ...records.map((record) => {
      const status = RELATIONSHIP_STATUS_LABELS[record.status] || record.status;
      const actions = el('div', { class: 'relationship-actions' });
      if (record.status !== 'approved') {
        actions.append(
          el(
            'button',
            {
              class: 'btn btn-ghost btn-sm',
              type: 'button',
              onClick: () =>
                changeRelationshipStatus(record, 'approved', refresh),
            },
            icon('check'),
            'Approve'
          )
        );
      }
      if (record.status !== 'rejected') {
        actions.append(
          el(
            'button',
            {
              class: 'btn btn-ghost btn-sm',
              type: 'button',
              onClick: () =>
                changeRelationshipStatus(record, 'rejected', refresh),
            },
            icon('x'),
            'Reject'
          )
        );
      }
      actions.append(
        el(
          'button',
          {
            class: 'btn btn-ghost btn-sm',
            type: 'button',
            onClick: () =>
              openRelationshipEditor({
                projectId,
                meta,
                characters,
                record,
                refresh,
              }),
          },
          icon('pencil'),
          'Edit'
        ),
        el(
          'button',
          {
            class: 'btn btn-ghost btn-sm',
            type: 'button',
            onClick: () => deleteRelationship(record, refresh),
          },
          icon('trash'),
          'Delete'
        )
      );

      return el(
        'article',
        { class: 'relationship-row recorded' },
        el(
          'div',
          { class: 'relationship-pair' },
          el('strong', {}, record.character_a_name),
          el('span', { class: 'relationship-join' }, '↔'),
          el('strong', {}, record.character_b_name),
          el(
            'span',
            { class: 'chip accent' },
            relationshipTypeLabel(meta, record.relation_type)
          ),
          el(
            'span',
            {
              class: `chip ${
                record.status === 'approved'
                  ? 'ok'
                  : record.status === 'proposed'
                    ? 'warn'
                    : ''
              }`.trim(),
            },
            status
          )
        ),
        record.description
          ? el('p', { class: 'relationship-note' }, record.description)
          : null,
        record.source_event_id
          ? el(
              'p',
              { class: 'hint' },
              'Source: ',
              el(
                'a',
                { href: `#/workspace/chapters/${record.source_chapter_id}` },
                `Chapter ${record.source_chapter_position} — ${record.source_chapter_title}`
              ),
              ` · ${record.source_summary}`
            )
          : null,
        actions
      );
    })
  );
}

function renderRelationships(pairs, host, error, meta, characters, refresh, projectId) {
  if (error) {
    host.replaceChildren(el('p', { class: 'hint' }, error));
    return;
  }
  if (!pairs.length) {
    host.replaceChildren(
      el(
        'div',
        { class: 'card card-pad' },
        el(
          'p',
          { class: 'hint' },
          'Character relationships appear when two linked profiles share an extracted event.'
        )
      )
    );
    return;
  }
  host.replaceChildren(
    ...pairs.map((pair) => {
      const latest = el(
        'a',
        { href: `#/workspace/chapters/${pair.latest_chapter_id}` },
        `Chapter ${pair.latest_chapter_position} — ${pair.latest_chapter_title}`
      );
      return el(
        'article',
        { class: 'relationship-row' },
        el(
          'div',
          { class: 'relationship-pair' },
          el('strong', {}, pair.character_a_name),
          el('span', { class: 'relationship-join' }, '↔'),
          el('strong', {}, pair.character_b_name),
          el(
            'span',
            { class: 'chip' },
            `${count(pair.shared_events)} shared event${pair.shared_events === 1 ? '' : 's'}`
          ),
          el(
            'button',
            {
              class: 'btn btn-ghost btn-sm',
              type: 'button',
              onClick: () =>
                openRelationshipEditor({
                  projectId,
                  meta,
                  characters,
                  pair,
                  refresh,
                }),
            },
            icon('plus'),
            'Record'
          )
        ),
        el(
          'p',
          { class: 'hint' },
          'Latest: ',
          pair.latest_summary,
          ' · ',
          latest
        )
      );
    })
  );
}

async function changeRelationshipStatus(record, status, refresh) {
  try {
    await api.patch(`/api/relationship-records/${record.id}/status`, {
      status,
    });
    toast(`Relationship ${status}.`, 'success');
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  }
}

function deleteRelationship(record, refresh) {
  confirmDialog({
    title: 'Delete relationship',
    message: `Remove the relationship record between ${record.character_a_name} and ${record.character_b_name}? This cannot be undone.`,
    confirmLabel: 'Delete record',
    onConfirm: async () => {
      try {
        await api.del(`/api/relationship-records/${record.id}`);
        toast('Relationship deleted.', 'success');
        await refresh();
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
}

function openRelationshipEditor({
  projectId,
  meta,
  characters,
  record = null,
  pair = null,
  refresh,
}) {
  const types = relationshipTypeOptions(meta);
  const type = select(
    types.map((item) => ({ value: item.key, label: item.label })),
    { value: record?.relation_type || types[0].key }
  );
  const description = textarea({
    rows: 3,
    value: record?.description || '',
  });
  let first = null;
  let second = null;
  const body = [];

  if (record) {
    body.push(
      el(
        'p',
        { class: 'relationship-pair' },
        el('strong', {}, record.character_a_name),
        el('span', { class: 'relationship-join' }, '↔'),
        el('strong', {}, record.character_b_name)
      )
    );
  } else {
    const options = characters.map((character) => ({
      value: character.id,
      label: character.name,
    }));
    first = select(options, {
      value: pair?.character_a_id ?? options[0]?.value,
    });
    second = select(options, {
      value: pair?.character_b_id ?? options[1]?.value,
    });
    if (pair) {
      first.disabled = true;
      second.disabled = true;
    }
    body.push(
      field('First character', first),
      field('Second character', second)
    );
    if (pair) {
      body.push(
        el(
          'p',
          { class: 'hint' },
          `Provenance: Chapter ${pair.latest_chapter_position} — ${pair.latest_chapter_title} · ${pair.latest_summary}`
        )
      );
    }
  }

  body.push(
    field('Relationship type', type),
    field(
      'Description',
      description,
      'Optional author note. Only approved records count as canon.'
    )
  );

  const save = el(
    'button',
    { class: 'btn btn-primary', type: 'button' },
    record ? 'Save record' : 'Record as proposed'
  );
  const modal = openModal({
    title: record ? 'Edit relationship record' : 'Record relationship',
    wide: true,
    body,
    footer: [
      el(
        'button',
        {
          class: 'btn btn-ghost',
          type: 'button',
          onClick: () => modal.close(),
        },
        'Cancel'
      ),
      save,
    ],
  });

  save.addEventListener('click', async () => {
    const payload = {
      relation_type: type.value,
      description: description.value.trim(),
    };
    if (!record) {
      if (!first?.value || !second?.value) {
        toast('Choose two characters.', 'error');
        return;
      }
      if (first.value === second.value) {
        toast('Choose two different characters.', 'error');
        return;
      }
    }
    modal.setBusy(true);
    try {
      if (record) {
        await api.patch(`/api/relationship-records/${record.id}`, payload);
        toast('Relationship updated.', 'success');
      } else {
        await api.post(
          `/api/projects/${projectId}/relationship-records`,
          {
            character_a_id: Number(first.value),
            character_b_id: Number(second.value),
            source_event_id: pair?.latest_event_id ?? null,
            ...payload,
          }
        );
        toast('Relationship recorded as proposed.', 'success');
      }
      modal.close();
      await refresh();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      modal.setBusy(false);
    }
  });
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
