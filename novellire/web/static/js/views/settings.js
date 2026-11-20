import { api } from '../api.js';
import {
  confirmDialog,
  el,
  field,
  icon,
  input,
  select,
  segmented,
  toast,
} from '../ui.js';

const DEFAULT_APPEARANCE = {
  theme: 'system',
  accent: 'violet',
  ui_font: 'system',
  reading_font: 'garamond',
  ui_font_size: 14,
  reading_font_size: 19,
  reading_width: 'standard',
};

const UI_FONT_LABELS = {
  system: 'System UI',
  humanist: 'Humanist sans',
  serif: 'Serif editorial',
  mono: 'Monospace',
};

const READING_FONT_LABELS = {
  garamond: 'Garamond',
  georgia: 'Georgia',
  palatino: 'Palatino',
};

const READING_FONT_STACKS = {
  garamond: '"EB Garamond", Garamond, Georgia, serif',
  georgia: 'Georgia, "Times New Roman", serif',
  palatino: '"Palatino Linotype", Palatino, Georgia, serif',
};

export function renderSettings(ctx) {
  const { state } = ctx;
  const appearance = state.settings.appearance;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'App settings'),
        el(
          'div',
          { class: 'sub' },
          'These settings apply to this installation: appearance, the local model connection, and data locations. Novel details live in Project settings.'
        )
      ),
      el(
        'div',
        { class: 'actions' },
        state.activeProjectId
          ? el(
              'a',
              { class: 'btn btn-sm', href: '#/project/settings' },
              icon('book'),
              'Project settings'
            )
          : null,
        el(
          'button',
          {
            class: 'btn btn-sm',
            type: 'button',
            onClick: () => ctx.saveAppearance(DEFAULT_APPEARANCE),
          },
          icon('refresh'),
          'Reset appearance'
        )
      )
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'settings-grid' },
      el('div', { class: 'settings-stack' }, appearanceCard(ctx, appearance), modelCard(ctx), privacyCard(ctx)),
      el('div', { class: 'settings-stack' }, aboutCard(state))
    )
  );

  return wrap;
}

/* -- appearance ----------------------------------------------------------- */

function appearanceCard(ctx, appearance) {
  const body = el('div', { class: 'settings-card-body' });

  body.append(
    el(
      'div',
      { class: 'setting-row', style: { flexDirection: 'column', alignItems: 'stretch' } },
      el(
        'div',
        { class: 'setting-label' },
        el('strong', {}, 'Theme'),
        el('small', {}, 'Follow the system, or pin a light or dark workspace.')
      ),
      themeCards(ctx, appearance.theme)
    )
  );

  body.append(
    el(
      'div',
      { class: 'setting-row' },
      el('div', { class: 'setting-label' }, el('strong', {}, 'Accent'), el('small', {}, 'Used for selection, focus, and primary actions.')),
      accentSwatches(ctx, appearance.accent)
    )
  );

  const uiFont = select(
    Object.entries(UI_FONT_LABELS).map(([value, label]) => ({ value, label })),
    { value: appearance.ui_font }
  );
  uiFont.addEventListener('change', () => ctx.saveAppearance({ ui_font: uiFont.value }));

  const readingFont = select(
    Object.entries(READING_FONT_LABELS).map(([value, label]) => ({ value, label })),
    { value: appearance.reading_font }
  );
  readingFont.addEventListener('change', () => ctx.saveAppearance({ reading_font: readingFont.value }));

  body.append(
    row('Interface font', 'Sidebar, forms, and metadata.', uiFont),
    row(
      'Reading font',
      'Manuscript surface in Preview.',
      el(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: '6px' } },
        readingFont,
        el(
          'div',
          {
            class: 'font-sample',
            style: { fontFamily: READING_FONT_STACKS[appearance.reading_font] || READING_FONT_STACKS.garamond },
          },
          'The vault door opened onto dust and brass.'
        )
      )
    )
  );

  const uiSize = range({
    min: 12,
    max: 18,
    step: 1,
    value: appearance.ui_font_size,
    suffix: 'px',
    onChange: (value) => ctx.saveAppearance({ ui_font_size: value }, { rerender: false }),
  });
  const readingSize = range({
    min: 15,
    max: 26,
    step: 1,
    value: appearance.reading_font_size,
    suffix: 'px',
    onChange: (value) => ctx.saveAppearance({ reading_font_size: value }, { rerender: false }),
  });

  body.append(
    row('Interface size', 'Comfortable on 1080p and laptop screens.', uiSize),
    row('Reading size', 'Applies to the manuscript surface.', readingSize),
    row(
      'Reading width',
      'Measure of the typeset page.',
      segmented(
        [
          { value: 'narrow', label: 'Narrow' },
          { value: 'standard', label: 'Standard' },
          { value: 'wide', label: 'Wide' },
        ],
        appearance.reading_width,
        (value) => ctx.saveAppearance({ reading_width: value })
      )
    )
  );

  return settingsCard('sliders', 'Appearance', 'Theme, accent, type, and reading surface.', body);
}

function themeCards(ctx, current) {
  const options = [
    { key: 'system', label: 'System' },
    { key: 'light', label: 'Light' },
    { key: 'dark', label: 'Dark' },
  ];
  const wrap = el('div', { class: 'theme-options' });
  for (const option of options) {
    wrap.append(
      el(
        'button',
        {
          class: 'theme-option',
          type: 'button',
          'aria-pressed': option.key === current ? 'true' : 'false',
          onClick: () => ctx.saveAppearance({ theme: option.key }),
        },
        el(
          'div',
          { class: `theme-preview ${option.key}` },
          el('div', { class: 'bar' }),
          el('div', { class: 'body' }, el('span'), el('span'), el('span'))
        ),
        el('span', {}, option.label)
      )
    );
  }
  return wrap;
}

function accentSwatches(ctx, current) {
  const wrap = el('div', { class: 'swatches' });
  for (const accent of ctx.state.meta.appearance_options.accents) {
    wrap.append(
      el('button', {
        class: 'swatch',
        type: 'button',
        dataset: { accent },
        title: accent[0].toUpperCase() + accent.slice(1),
        'aria-label': `${accent} accent`,
        'aria-pressed': accent === current ? 'true' : 'false',
        onClick: () => ctx.saveAppearance({ accent }),
      })
    );
  }
  return wrap;
}

/* -- model and generation ------------------------------------------------- */

function modelCard(ctx) {
  const { state } = ctx;
  const generation = state.settings.generation;
  const ollama = state.ollama || { available: false, models: [] };
  const body = el('div', { class: 'settings-card-body' });

  const status = el(
    'div',
    { class: 'setting-row' },
    el(
      'div',
      { class: 'setting-label' },
      el(
        'strong',
        { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
        el('span', { class: `status-dot ${ollama.available ? 'online' : 'offline'}` }),
        ollama.available ? 'Ollama connected' : 'Ollama offline'
      ),
      el('small', {}, `${state.settings.provider.base_url} · loopback only. Start it with \`ollama serve\`.`)
    ),
    el(
      'div',
      { class: 'setting-control' },
      el(
        'button',
        {
          class: 'btn btn-sm',
          type: 'button',
          onClick: async () => {
            await ctx.refreshOllama();
            toast('Connection status refreshed.', 'success');
          },
        },
        icon('refresh'),
        'Test connection'
      )
    )
  );
  body.append(status);

  if (ollama.error) {
    body.append(el('p', { class: 'hint', style: { color: 'var(--muted)' } }, ollama.error));
  }

  const modelNames = (ollama.models || []).map((model) => model.name);
  if (generation.model && !modelNames.includes(generation.model)) modelNames.unshift(generation.model);
  const model = select(
    modelNames.length
      ? modelNames.map((name) => ({ value: name, label: name }))
      : [{ value: '', label: 'No models installed' }],
    { value: generation.model || '' }
  );

  const temperature = range({
    min: 0,
    max: 2,
    step: 0.05,
    value: generation.temperature,
    suffix: '',
    fixed: 2,
    onChange: () => {},
  });
  const topP = range({
    min: 0.05,
    max: 1,
    step: 0.05,
    value: generation.top_p,
    suffix: '',
    fixed: 2,
    onChange: () => {},
  });
  const numPredict = input({
    type: 'number',
    min: '32',
    max: '8192',
    step: '1',
    value: String(generation.num_predict),
  });
  const contextWindow = select(
    [2048, 4096, 8192, 16384].map((value) => ({ value: String(value), label: `${value} tokens` })),
    { value: String(generation.context_window) }
  );

  body.append(
    row('Default model', 'Discoverable from the local Ollama server.', model),
    row('Temperature', 'Lower is consistent; higher is varied.', temperature),
    row('Top-p', 'Nucleus sampling cutoff.', topP),
    row('Maximum output tokens', 'Caps generation length and memory use.', numPredict),
    row('Context window', 'Passed as num_ctx. Larger windows cost RAM.', contextWindow)
  );

  body.append(
    el(
      'div',
      { class: 'form-actions' },
      el(
        'button',
        {
          class: 'btn btn-primary',
          type: 'button',
          onClick: async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
              const saved = await api.put('/api/settings/generation', {
                model: model.value,
                temperature: Number(temperature.querySelector('input').value),
                top_p: Number(topP.querySelector('input').value),
                num_predict: Number(numPredict.value),
                context_window: Number(contextWindow.value),
              });
              ctx.state.settings.generation = saved;
              toast('Writing defaults saved.', 'success');
            } catch (error) {
              toast(error.message, 'error');
            } finally {
              button.disabled = false;
            }
          },
        },
        'Save defaults'
      ),
      el('span', { class: 'hint' }, 'Only one model is loaded at a time.')
    )
  );

  const future = el(
    'div',
    { class: 'cloud-card', style: { marginTop: '8px' } },
    icon('sparkles'),
    el(
      'div',
      { class: 'text' },
      el('strong', {}, 'Cloud API providers — planned'),
      el(
        'p',
        {},
        'A later release adds opt-in hosted providers next to local models. Nothing is sent off-device unless you configure a provider and choose it explicitly.'
      )
    )
  );
  body.append(future);

  return settingsCard('layers', 'Writing model', 'Ollama connection and app-wide generation defaults.', body);
}

/* -- data and privacy ----------------------------------------------------- */

function privacyCard(ctx) {
  const { state } = ctx;
  const body = el('div', { class: 'settings-card-body' });
  body.append(
    el(
      'div',
      { class: 'setting-row' },
      el(
        'div',
        { class: 'setting-label' },
        el('strong', {}, 'Inference mode'),
        el('small', {}, 'Local models keep the manuscript on this machine. Cloud providers will be opt-in and clearly labelled.')
      ),
      el('div', { class: 'setting-control' }, el('span', { class: 'chip ok' }, 'Local (Ollama)'))
    )
  );

  body.append(
    el(
      'div',
      { class: 'stat-list' },
      statLine('Data directory', state.settings.paths.data_dir),
      statLine('Database', state.settings.paths.database),
      statLine('Schema version', state.settings.schema_version),
      statLine('Application version', state.settings.version)
    )
  );

  const download = el(
    'a',
    { class: 'btn btn-sm', href: '/api/backup', download: '' },
    icon('download'),
    'Download backup'
  );
  const filePicker = input({
    type: 'file',
    accept: '.db,application/vnd.sqlite3,application/octet-stream',
  });
  filePicker.style.display = 'none';
  filePicker.addEventListener('change', () => {
    const file = filePicker.files?.[0];
    filePicker.value = '';
    if (file) openRestoreDialog(file);
  });
  const restore = el(
    'label',
    { class: 'btn btn-sm' },
    icon('refresh'),
    'Restore backup',
    filePicker
  );

  body.append(
    row(
      'Backups',
      'A snapshot includes every project, chapter, document, summary, event, and setting. Safety copies are kept in the data directory under backups.',
      el('div', { class: 'actions' }, download, restore)
    )
  );

  return settingsCard('shield', 'Data and privacy', 'Where this installation keeps its data.', body);
}

async function openRestoreDialog(file) {
  let report;
  try {
    const response = await fetch('/api/backup/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      toast(
        payload?.detail || `That file could not be verified (${response.status}).`,
        'error'
      );
      return;
    }
    report = payload;
  } catch (error) {
    toast('Cannot reach the Novellire server. Is it still running?', 'error');
    return;
  }

  const size = `${(report.size_bytes / (1024 * 1024)).toFixed(1)} MB`;
  const upgrade = report.upgrade_required
    ? ' It was made by an older version and will be upgraded during restore.'
    : '';
  confirmDialog({
    title: 'Restore verified backup',
    message: `“${file.name}” passed verification: schema ${report.schema_version}, ${report.projects} project${report.projects === 1 ? '' : 's'}, ${report.chapters} chapter${report.chapters === 1 ? '' : 's'}, ${size}.${upgrade} It will replace every project and memory record in this installation. A safety copy of the current database is kept in the backups folder before anything changes.`,
    confirmLabel: 'Restore backup',
    onConfirm: async () => {
      let response;
      try {
        response = await fetch('/api/backup/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream' },
          body: file,
        });
      } catch (error) {
        toast('Cannot reach the Novellire server. Is it still running?', 'error');
        return;
      }
      let payload = null;
      try {
        payload = await response.json();
      } catch (error) { /* fall through to the status */ }
      if (!response.ok) {
        toast(payload?.detail || `Restore failed (${response.status}).`, 'error');
        return;
      }
      toast(
        `Backup restored: ${payload.projects} projects, ${payload.chapters} chapters.`,
        'success'
      );
      window.setTimeout(() => window.location.reload(), 900);
    },
  });
}

function aboutCard(state) {
  const body = el('div', { class: 'settings-card-body' });
  body.append(
    el(
      'div',
      { class: 'stat-list' },
      statLine('Version', state.settings.version),
      statLine('Schema', state.settings.schema_version),
      statLine('Provider', 'Ollama (local)')
    ),
    el(
      'p',
      { class: 'hint', style: { marginTop: '14px' } },
      'No telemetry and no analytics. While a local model is selected, no project content leaves this machine.'
    )
  );
  return settingsCard('feather', 'About', 'Build information.', body);
}

/* -- primitives ----------------------------------------------------------- */

function settingsCard(iconName, title, subtitle, body) {
  return el(
    'section',
    { class: 'card settings-card' },
    el(
      'div',
      { class: 'settings-card-head' },
      icon(iconName),
      el('div', {}, el('h2', {}, title), el('p', {}, subtitle))
    ),
    body
  );
}

function row(label, description, control) {
  return el(
    'div',
    { class: 'setting-row' },
    el('div', { class: 'setting-label' }, el('strong', {}, label), description ? el('small', {}, description) : null),
    el('div', { class: 'setting-control' }, control)
  );
}

function statLine(label, value) {
  return el('div', { class: 'stat-line' }, el('span', {}, label), el('code', { title: String(value) }, String(value)));
}

function range({ min, max, step, value, suffix = '', fixed = 0, onChange }) {
  const slider = input({ type: 'range', min: String(min), max: String(max), step: String(step), value: String(value) });
  const output = el('span', { class: 'chip' }, `${Number(value).toFixed(fixed)}${suffix}`);
  slider.addEventListener('input', () => {
    output.textContent = `${Number(slider.value).toFixed(fixed)}${suffix}`;
  });
  slider.addEventListener('change', () => onChange(Number(slider.value)));
  return el('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', minWidth: '220px' } }, slider, output);
}
