import { api } from '../api.js';
import {
  count,
  el,
  field,
  icon,
  input,
  openModal,
  toast,
} from '../ui.js';

const FIELD_LABELS = {
  location: 'Location',
  status: 'Status',
  goals: 'Goals',
  knowledge: 'Knowledge',
};

export function openStateProposalDialog(ctx, chapter) {
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
    title: `State updates · chapter ${chapter.position}`,
    wide: true,
    body: [
      el(
        'p',
        { class: 'hint' },
        'Novellire reads the saved chapter and proposes what changed for its characters. Nothing is recorded until you apply; edit any field first.'
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
    .post(`/api/chapters/${chapter.id}/state-proposals`, {
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
        const values = {};
        for (const key of Object.keys(FIELD_LABELS)) {
          values[key] = input({ value: proposal[key] || '' });
        }
        return { proposal, selected, values };
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
                    el('strong', {}, row.proposal.character_name),
                    el(
                      'span',
                      { class: 'chip' },
                      row.proposal.existing_state_id
                        ? 'updates this chapter’s snapshot'
                        : 'new snapshot'
                    )
                  ),
                  ...Object.entries(FIELD_LABELS).map(([key, label]) =>
                    field(label, row.values[key])
                  )
                )
              )
            )
          : el('p', { class: 'hint' }, 'No state changes were detected in this chapter.')
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
        character_id: row.proposal.character_id,
        location: row.values.location.value,
        status: row.values.status.value,
        goals: row.values.goals.value,
        knowledge: row.values.knowledge.value,
      }));
    if (!updates.length) {
      toast('Select at least one update.', 'error');
      return;
    }
    apply.disabled = true;
    try {
      const result = await api.post(
        `/api/chapters/${chapter.id}/state-proposals/apply`,
        { updates }
      );
      const total = result.states?.length || 0;
      modal.close();
      toast(
        `${count(total)} state snapshot${total === 1 ? '' : 's'} recorded.`,
        'success'
      );
      await ctx.refresh();
    } catch (error) {
      toast(error.message, 'error');
      apply.disabled = false;
    }
  });
}
