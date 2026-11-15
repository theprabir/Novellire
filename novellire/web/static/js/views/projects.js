import { api } from '../api.js';
import {
  closeModal,
  confirmDialog,
  count,
  el,
  emptyState,
  field,
  icon,
  initials,
  input,
  openModal,
  textarea,
  toast,
} from '../ui.js';

export function renderProjects(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Projects'),
        el(
          'div',
          { class: 'sub' },
          'Each project keeps its own story bible, cast, chapter map, and generation history. Nothing is shared between projects.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        el(
          'button',
          { class: 'btn btn-primary', type: 'button', onClick: () => openProjectForm(ctx) },
          icon('plus'),
          'New project'
        )
      )
    )
  );

  if (!state.projects.length) {
    wrap.append(
      emptyState({
        iconName: 'feather',
        title: 'No projects yet',
        body: 'Create a project to begin a novel. Novellire keeps the chapter map, story bible, and character profiles separate for every book.',
        action: el(
          'button',
          { class: 'btn btn-primary', type: 'button', onClick: () => openProjectForm(ctx) },
          icon('plus'),
          'Create your first project'
        ),
      })
    );
    return wrap;
  }

  const grid = el('div', { class: 'project-grid' });
  for (const project of state.projects) grid.append(projectCard(ctx, project));
  wrap.append(grid);
  return wrap;
}

function projectCard(ctx, project) {
  const active = project.id === ctx.state.activeProjectId;
  const target = Number(project.target_word_count || 0);
  const percent = target ? Math.min(100, Math.round((project.words_generated / target) * 100)) : 0;

  return el(
    'article',
    { class: 'project-card' },
    el(
      'div',
      { class: 'project-cover' },
      el('span', { class: 'initial' }, initials(project.name)),
      el('span', { class: 'genre' }, project.genre || 'Unspecified genre')
    ),
    el(
      'div',
      { class: 'project-body' },
      el('h3', {}, project.name),
      el('p', { class: 'desc' }, project.description || 'No premise recorded yet.'),
      el(
        'div',
        { class: 'project-meta' },
        active ? el('span', { class: 'chip accent' }, 'Active') : null,
        el('span', { class: 'stat' }, `${count(project.words_generated)} words`),
        el('span', { class: 'stat' }, `${count(project.generations)} generations`)
      ),
      target
        ? el(
            'div',
            { class: 'progress', title: `${percent}% of ${count(target)} words` },
            el('span', { style: { width: `${percent}%` } })
          )
        : null,
      target
        ? el('div', { class: 'hint' }, `${percent}% of ${count(target)} word target`)
        : null
    ),
    el(
      'div',
      { class: 'project-actions' },
      el(
        'button',
        {
          class: 'btn btn-primary btn-sm',
          type: 'button',
          onClick: () => ctx.selectProject(project.id),
        },
        'Open'
      ),
      el(
        'button',
        {
          class: 'btn btn-sm',
          type: 'button',
          onClick: () => openProjectForm(ctx, project),
        },
        'Edit'
      ),
      el(
        'button',
        {
          class: 'btn btn-ghost btn-sm',
          type: 'button',
          onClick: () => archiveProject(ctx, project),
        },
        'Archive'
      )
    )
  );
}

function openProjectForm(ctx, project = null) {
  const isEdit = Boolean(project);
  const name = input({
    value: project?.name || '',
    placeholder: 'The Ashfall Chronicle',
    get required() { return true; },
    maxlength: '120',
  });
  const description = textarea({
    value: project?.description || '',
    rows: 3,
    placeholder: 'One or two sentences about the story.',
  });
  const genre = input({ value: project?.genre || '', placeholder: 'Science fiction' });
  const style = input({
    value: project?.narrative_style || '',
    placeholder: 'Close third person, past tense',
  });
  const target = input({
    type: 'number',
    min: '0',
    max: '20000000',
    step: '1000',
    value: String(project?.target_word_count || 0),
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
      el('button', { class: 'btn btn-primary', type: 'submit' }, isEdit ? 'Save project' : 'Create project'),
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel')
    )
  );

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      name: name.value,
      description: description.value,
      genre: genre.value,
      narrative_style: style.value,
      target_word_count: Number(target.value) || null,
    };
    try {
      if (isEdit) {
        await api.patch(`/api/projects/${project.id}`, payload);
        await ctx.reloadProjects();
        toast('Project updated.', 'success');
        closeModal();
      } else {
        const created = await api.post('/api/projects', payload);
        await ctx.reloadProjects();
        await ctx.selectProject(created.id);
        toast(`Created “${created.name}”.`, 'success');
        closeModal();
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  openModal({ title: isEdit ? 'Edit project' : 'New project', body: form });
}

function archiveProject(ctx, project) {
  confirmDialog({
    title: 'Archive project',
    message: `“${project.name}” will be hidden from the project list. Its chapters, characters, and generations stay in the database.`,
    confirmLabel: 'Archive project',
    onConfirm: async () => {
      try {
        await api.post(`/api/projects/${project.id}/archive`, {});
        await ctx.reloadProjects();
        toast('Project archived.', 'success');
      } catch (error) {
        toast(error.message, 'error');
      }
    },
  });
}
