import { count, el, emptyState, icon, initials } from '../ui.js';
import { openProjectForm, projectCard } from './projects.js';

export function renderHome(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Home'),
        el(
          'div',
          { class: 'sub' },
          'Your library of novels. Home is the overview; opening a project takes you to its workspace, documents, and chapters.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        socialLink('github', 'GitHub', 'https://github.com/theprabir'),
        socialLink('instagram', 'Instagram', 'https://instagram.com/prabir.exe'),
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
        body: 'Create a project to begin a novel. Every project keeps its own documents, chapters, and generation history.',
        action: el(
          'button',
          { class: 'btn btn-primary', type: 'button', onClick: () => openProjectForm(ctx) },
          icon('plus'),
          'Create your first project'
        ),
      }),
      profileCard()
    );
    return wrap;
  }

  const active = state.projects.find((project) => project.id === state.activeProjectId);
  if (active) wrap.append(continueCard(active));

  wrap.append(
    el(
      'div',
      { class: 'section-head' },
      el('h2', {}, 'All projects'),
      el('span', { class: 'hint' }, `${count(state.projects.length)} in this library`)
    )
  );

  const grid = el('div', { class: 'project-grid' });
  for (const project of state.projects) grid.append(projectCard(ctx, project));
  wrap.append(grid, profileCard());
  return wrap;
}

function continueCard(project) {
  return el(
    'section',
    { class: 'card home-continue' },
    el('span', { class: 'continue-cover' }, initials(project.name)),
    el(
      'div',
      { class: 'continue-copy' },
      el('span', { class: 'eyebrow' }, 'Continue writing'),
      el('h2', {}, project.name),
      el(
        'p',
        { class: 'hint' },
        `${count(project.words_generated)} words drafted · ${count(project.generations)} generations · ${
          project.genre || 'No genre set'
        }`
      )
    ),
    el(
      'div',
      { class: 'actions' },
      el('a', { class: 'btn btn-primary', href: '#/workspace' }, icon('layers'), 'Open workspace'),
      el(
        'a',
        { class: 'btn btn-sm', href: '#/project/settings' },
        icon('settings'),
        'Project settings'
      )
    )
  );
}

export function socialLink(iconName, label, href) {
  return el(
    'a',
    {
      class: 'btn btn-sm',
      href,
      target: '_blank',
      rel: 'noopener noreferrer',
      title: label,
    },
    icon(iconName),
    label
  );
}

function profileCard() {
  return el(
    'section',
    { class: 'card profile-card' },
    el('span', { class: 'profile-mark' }, icon('feather')),
    el(
      'div',
      { class: 'profile-copy' },
      el('h2', {}, 'Built by Prabir Kumar Das'),
      el(
        'p',
        { class: 'hint' },
        'Novellire is an independent, local-first writing harness. Follow the build or say hello.'
      )
    ),
    el(
      'div',
      { class: 'actions' },
      socialLink('github', 'GitHub', 'https://github.com/theprabir'),
      socialLink('instagram', 'Instagram', 'https://instagram.com/prabir.exe')
    )
  );
}
