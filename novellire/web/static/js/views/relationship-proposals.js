import { api } from '../api.js';
import {
  count,
  el,
  field,
  icon,
  input,
  openModal,
  select,
  toast,
} from '../ui.js';

const TYPE_OPTIONS = [
  { value: 'ally', label: 'Ally' },
  { value: 'rival', label: 'Rival' },
  { value: 'family', label: 'Family' },
  { value: 'mentor', label: 'Mentor' },
  { value: 'romantic', label: 'Romantic' },
  { value: 'debt', label: 'Debt' },
  { value: 'other', label: 'Other' },
];

export function openRelationshipProposalDialog(ctx, chapter) {
  const state = ctx.state;
  const settings = state.settings?.generation || {};
  const model = settings.model || state.ollama?.models?.[0]?.name || '';
  const host = el('div', { class: 'review-findings' });
  let rows = [];

  const apply = el(
    'button',
    { class: 'btn btn-primary', type: 'button', disabled: true },
    icon('check'),
    'Apply selected'
  );
  const modal = openModal({
    title: `Relationship changes · chapter ${chapter.position}`,
    wide: true,
    body: [
      el(
        'p',
        { class: 'hint' },
        'Novellire reads the saved chapter and proposes how pairs of characters now stand. Nothing is recorded until you apply; edit any field first. Applying records each relationship’s state for this chapter, so the Continuity ledger shows how it evolved.'
      ),
      host,
    ],
    footer: [
      el(
        'button',
        { class: 'btn btn-ghost', type: 'button', onClick: () => modal.close() },
        'Close'
      ),
      apply,
    ],
  });

  if (!(chapter.content || '').trim()) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Write or draft this chapter first.')
    );
    return;
  }
  if (!model) {
    host.replaceChildren(
      el('p', { class: 'hint' }, 'Choose a model in Settings first.')
    );
    return;
  }

  host.replaceChildren(el('p', { class: 'hint' }, 'Reading the chapter…'));
  api
    .post(`/api/chapters/${chapter.id}/relationship-proposals`, {
      model,
      temperature: Number(settings.temperature ?? 0.2),
      top_p: Number(settings.top_p ?? 0.9),
      num_predict: Number(settings.num_predict ?? 700),
      context_window: Number(settings.context_window ?? 4096),
    })
    .then((result) => {
      const proposals = result.proposals || [];
      rows = proposals.map((proposal) => {
        const selected = input({ type: 'checkbox' });
        selected.checked = true;
        return {
          proposal,
          selected,
          relationType: select(TYPE_OPTIONS, { value: proposal.relation_type }),
          description: input({ value: proposal.description || '' }),
        };
      });
      host.replaceChildren(
        rows.length
          ? el(
              'div',
              { class: 'ledger-list' },
              rows.map((row) =>
                el(
                  'div',
                  { class: 'ledger-row' },
                  el(
                    'div',
                    { class: 'review-finding-head' },
                    row.selected,
                    el(
                      'strong',
                      {},
                      `${row.proposal.character_a_name} and ${row.proposal.character_b_name}`
                    ),
                    el(
                      'span',
                      { class: 'chip' },
                      row.proposal.existing_relationship_id
                        ? `updates recorded relationship (${row.proposal.existing_status})`
                        : 'new relationship'
                    )
                  ),
                  field('Type', row.relationType),
                  field('How they stand now', row.description)
                )
              )
            )
          : el(
              'p',
              { class: 'hint' },
              'No relationship changes were detected in this chapter.'
            )
      );
      apply.disabled = rows.length === 0;
    })
    .catch((error) => {
      host.replaceChildren(el('p', { class: 'hint' }, error.message));
    });

  apply.addEventListener('click', async () => {
    const updates = rows
      .filter((row) => row.selected.checked)
      .map((row) => ({
        character_a_id: row.proposal.character_a_id,
        character_b_id: row.proposal.character_b_id,
        relation_type: row.relationType.value,
        description: row.description.value,
      }));
    if (!updates.length) {
      toast('Select at least one change.', 'error');
      return;
    }
    apply.disabled = true;
    try {
      const result = await api.post(
        `/api/chapters/${chapter.id}/relationship-proposals/apply`,
        { updates }
      );
      const total = result.relationships?.length || 0;
      modal.close();
      toast(
        `${count(total)} relationship${total === 1 ? '' : 's'} recorded for this chapter.`,
        'success'
      );
      await ctx.refresh();
    } catch (error) {
      toast(error.message, 'error');
      apply.disabled = false;
    }
  });
}
