import { api } from '../api.js';
import {
  count,
  el,
  emptyState,
  field,
  icon,
  input,
  select,
  toast,
} from '../ui.js';

export function renderExport(ctx) {
  const { state } = ctx;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Export'),
        el(
          'div',
          { class: 'sub' },
          'Compile this project’s chapters into a clean file. Prose is copied as written; nothing is rewritten or sent anywhere.'
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
        iconName: 'download',
        title: 'No project selected',
        body: 'Open a project before exporting its manuscript.',
        action: el('a', { class: 'btn btn-primary', href: '#/home' }, 'Go home'),
      })
    );
    return wrap;
  }

  const project = state.tree.project;
  const chapters = state.manuscript?.chapters || [];
  const written = chapters.filter((chapter) => chapter.content.trim());

  if (!written.length) {
    wrap.append(
      emptyState({
        iconName: 'download',
        title: 'Nothing to export yet',
        body: 'Add a chapter with text in the workspace, then come back to compile it.',
        action: el('a', { class: 'btn btn-primary', href: '#/workspace/chapters' }, 'Open chapters'),
      })
    );
    return wrap;
  }

  const format = select(
    [
      { value: 'markdown', label: 'Markdown (.md)' },
      { value: 'text', label: 'Plain text (.txt)' },
    ],
    { value: 'markdown' }
  );
  const includeDocuments = input({ type: 'checkbox' });
  const includeLabel = el(
    'label',
    { class: 'checkbox-row' },
    includeDocuments,
    el('span', {}, 'Append the four project documents')
  );
  format.addEventListener('change', () => {
    const text = format.value === 'text';
    includeDocuments.disabled = text;
    if (text) includeDocuments.checked = false;
    includeLabel.classList.toggle('is-disabled', text);
  });

  const prepare = el(
    'button',
    { class: 'btn btn-primary', type: 'button' },
    icon('download'),
    'Prepare export'
  );
  const output = el(
    'div',
    { class: 'export-output' },
    el(
      'p',
      { class: 'hint' },
      `${count(written.length)} chapter${written.length === 1 ? '' : 's'} ready · ${count(
        state.tree.stats.words
      )} words. Choose a format and prepare the file.`
    )
  );

  prepare.addEventListener('click', async () => {
    prepare.disabled = true;
    prepare.replaceChildren(icon('refresh'), 'Preparing…');
    try {
      const result = await api.get(
        `/api/projects/${project.id}/export?format=${format.value}&include_documents=${
          includeDocuments.checked ? 'true' : 'false'
        }`
      );
      output.replaceChildren(resultView(result));
      toast(`${result.filename} prepared.`, 'success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      prepare.disabled = false;
      prepare.replaceChildren(icon('download'), 'Prepare export');
    }
  });

  wrap.append(
    el(
      'div',
      { class: 'settings-grid' },
      el(
        'div',
        { class: 'settings-stack' },
        el(
          'section',
          { class: 'card settings-card' },
          el(
            'div',
            { class: 'settings-card-head' },
            icon('file'),
            el(
              'div',
              {},
              el('h2', {}, 'Manuscript file'),
              el('p', {}, 'Chapters in order, with titles and prose.')
            )
          ),
          el(
            'div',
            { class: 'settings-card-body' },
            el(
              'div',
              { class: 'form-grid' },
              field('Format', format),
              el(
                'div',
                { class: 'field' },
                el('span', { class: 'label' }, 'Appendix'),
                includeLabel
              ),
              el(
                'div',
                { class: 'form-actions span-2' },
                prepare,
                el('span', { class: 'hint' }, 'Files are generated on this machine.')
              )
            )
          )
        ),
        output
      ),
      el(
        'div',
        { class: 'settings-stack' },
        el(
          'section',
          { class: 'card settings-card' },
          el(
            'div',
            { class: 'settings-card-head' },
            icon('book'),
            el(
              'div',
              {},
              el('h2', {}, 'What is included'),
              el('p', {}, 'Only stored text is exported.')
            )
          ),
          el(
            'div',
            { class: 'settings-card-body' },
            el(
              'div',
              { class: 'stat-list' },
              statLine('Project', project.name),
              statLine('Chapters with text', written.length),
              statLine('Manuscript words', count(state.tree.stats.words)),
              statLine('Documents', 'Optional appendix'),
              statLine('Cover image', 'Not included')
            ),
            el(
              'p',
              { class: 'hint', style: { marginTop: '14px' } },
              'Markdown uses headings for the project and each chapter. Plain text keeps only the title, chapter headings, and prose.'
            )
          )
        )
      )
    )
  );

  return wrap;
}

function resultView(result) {
  const preview = result.content.length > 2400
    ? `${result.content.slice(0, 2400).trimEnd()}\n\n…`
    : result.content;

  return el(
    'section',
    { class: 'card settings-card' },
    el(
      'div',
      { class: 'settings-card-head' },
      icon('check'),
      el(
        'div',
        {},
        el('h2', {}, result.filename),
        el(
          'p',
          {},
          `${count(result.word_count)} words · ${result.format === 'markdown' ? 'Markdown' : 'Plain text'}`
        )
      )
    ),
    el(
      'div',
      { class: 'settings-card-body' },
      el('pre', { class: 'export-preview' }, preview),
      el(
        'div',
        { class: 'form-actions' },
        el(
          'button',
          {
            class: 'btn btn-primary',
            type: 'button',
            onClick: () => download(result.filename, result.content, result.content_type),
          },
          icon('download'),
          'Download'
        ),
        el(
          'button',
          {
            class: 'btn btn-ghost',
            type: 'button',
            onClick: () => copyToClipboard(result.content),
          },
          icon('copy'),
          'Copy'
        ),
        el(
          'span',
          { class: 'hint' },
          `Saved to your browser’s downloads as ${result.filename}.`
        )
      )
    )
  );
}

function download(filename, content, contentType) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = el('a', { href: url, download: filename });
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function copyToClipboard(content) {
  try {
    await navigator.clipboard.writeText(content);
    toast('Manuscript copied.', 'success');
  } catch (error) {
    toast('Could not copy. Use Download instead.', 'error');
  }
}

function statLine(label, value) {
  return el(
    'div',
    { class: 'stat-line' },
    el('span', {}, label),
    el('span', {}, String(value))
  );
}
