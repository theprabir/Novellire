import { api } from '../api.js';
import {
  confirmDialog,
  el,
  emptyState,
  field,
  icon,
  input,
  textarea,
  toast,
} from '../ui.js';

export function renderProjectSettings(ctx) {
  const { state } = ctx;
  const project = state.projects.find((item) => item.id === state.activeProjectId);
  const wrap = el('div', { class: 'view-inner' });

  if (!project) {
    wrap.append(
      el('div', { class: 'page-head' }, el('div', {}, el('h1', {}, 'Project settings'))),
      emptyState({
        iconName: 'settings',
        title: 'No project selected',
        body: 'Open a project from Home before editing its details.',
        action: el('a', { class: 'btn btn-primary', href: '#/home' }, 'Go home'),
      })
    );
    return wrap;
  }

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Project settings'),
        el(
          'div',
          { class: 'sub' },
          `Details for “${project.name}”. Appearance, model connection, and data locations are app settings, not project settings.`
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el('a', { class: 'btn btn-sm', href: '#/workspace' }, icon('layers'), 'Workspace'),
        el('a', { class: 'btn btn-sm', href: '#/settings' }, icon('sliders'), 'App settings')
      )
    )
  );

  wrap.append(detailsCard(ctx, project));
  wrap.append(archiveCard(ctx, project));
  return wrap;
}

function detailsCard(ctx, project) {
  const name = input({
    value: project.name,
    placeholder: 'The Ashfall Chronicle',
    get required() { return true; },
    maxlength: '120',
  });
  const description = textarea({
    value: project.description || '',
    rows: 3,
    placeholder: 'One or two sentences about the story.',
  });
  const genre = input({ value: project.genre || '', placeholder: 'Science fiction' });
  const style = input({
    value: project.narrative_style || '',
    placeholder: 'Close third person, past tense',
  });
  const target = input({
    type: 'number',
    min: '0',
    max: '20000000',
    step: '1000',
    value: String(project.target_word_count || 0),
  });

  const form = el(
    'form',
    { class: 'form-grid' },
    el('div', { class: 'span-2' }, field('Project name', name)),
    el('div', { class: 'span-2' }, field('Premise', description)),
    field('Genre', genre),
    field('Narrative style', style),
    field('Target word count', target, 'Leave at 0 to skip a target.'),
    el(
      'div',
      { class: 'form-actions span-2' },
      el('button', { class: 'btn btn-primary', type: 'submit' }, 'Save project'),
      el('span', { class: 'hint' }, 'These details stay with this project only.')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      await api.patch(`/api/projects/${project.id}`, {
        name: name.value,
        description: description.value,
        genre: genre.value,
        narrative_style: style.value,
        target_word_count: Number(target.value) || null,
      });
      await ctx.reloadProjects();
      toast('Project details saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });

  return el(
    'section',
    { class: 'card settings-card' },
    el(
      'div',
      { class: 'settings-card-head' },
      icon('book'),
      el('div', {}, el('h2', {}, 'Novel details'), el('p', {}, 'Title, premise, genre, and writing target.'))
    ),
    el('div', { class: 'settings-card-body' }, form)
  );
}

function archiveCard(ctx, project) {
  return el(
    'section',
    { class: 'card settings-card danger-card' },
    el(
      'div',
      { class: 'settings-card-head' },
      icon('alert'),
      el(
        'div',
        {},
        el('h2', {}, 'Archive project'),
        el('p', {}, 'Hide this project from Home. Its documents, chapters, and generations stay in the database.')
      )
    ),
    el(
      'div',
      { class: 'settings-card-body' },
      el(
        'div',
        { class: 'form-actions' },
        el(
          'button',
          {
            class: 'btn btn-ghost',
            type: 'button',
            onClick: () =>
              confirmDialog({
                title: 'Archive project',
                message: `“${project.name}” will be hidden from the project list. Its documents, chapters, and generations stay in the database.`,
                confirmLabel: 'Archive project',
                onConfirm: async () => {
                  try {
                    await api.post(`/api/projects/${project.id}/archive`, {});
                    await ctx.reloadProjects();
                    window.location.hash = '#/home';
                    toast('Project archived.', 'success');
                  } catch (error) {
                    toast(error.message, 'error');
                  }
                },
              }),
          },
          icon('alert'),
          'Archive project'
        )
      )
    )
  );
}
