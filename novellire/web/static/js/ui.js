/* DOM and presentation helpers. All author text goes in through textContent. */

let fieldCounter = 0;

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key === 'value' && 'value' in node) node.value = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  appendChildren(node, children);
  return node;
}

function appendChildren(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) { appendChildren(parent, child); continue; }
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

const SVG_NS = 'http://www.w3.org/2000/svg';

export function icon(name, className = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', className);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

export function field(labelText, control, hint) {
  const id = control.id || `field-${++fieldCounter}`;
  control.id = id;
  return el(
    'div',
    { class: 'field' },
    el('label', { class: 'label', for: id }, labelText),
    control,
    hint ? el('div', { class: 'hint' }, hint) : null
  );
}

export function input(props = {}) {
  return el('input', { class: 'input', type: 'text', ...props });
}

export function textarea(props = {}) {
  const { value = '', ...rest } = props;
  const node = el('textarea', { class: 'textarea', ...rest });
  node.value = value;
  return node;
}

export function select(options, { value, ...props } = {}) {
  const node = el('select', { class: 'select', ...props });
  for (const option of options) {
    const item = typeof option === 'string' ? { value: option, label: option } : option;
    const opt = el('option', { value: item.value }, item.label);
    if (String(item.value) === String(value ?? '')) opt.selected = true;
    node.append(opt);
  }
  return node;
}

export function segmented(options, activeValue, onChange) {
  const wrap = el('div', { class: 'segmented', role: 'group' });
  for (const option of options) {
    const item = typeof option === 'string' ? { value: option, label: option } : option;
    const pressed = String(item.value) === String(activeValue);
    wrap.append(
      el(
        'button',
        {
          type: 'button',
          'aria-pressed': pressed ? 'true' : 'false',
          onClick: () => onChange(item.value),
        },
        item.icon ? icon(item.icon, 'icon') : null,
        item.label
      )
    );
  }
  return wrap;
}

export function emptyState({ iconName = 'sparkles', title, body, action = null }) {
  return el(
    'div',
    { class: 'empty' },
    icon(iconName, 'icon'),
    el('h3', {}, title),
    body ? el('p', {}, body) : null,
    action
  );
}

export function statusChip(key, meta) {
  const label = (meta?.work_statuses || []).find((item) => item.key === key)?.label || key;
  const tone = key === 'approved' ? 'ok' : key === 'drafting' ? 'warn' : '';
  return el('span', { class: `chip ${tone}`.trim() }, label);
}

export function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function initials(name) {
  const parts = String(name || '')
    .trim()
    .split(/\s+/)
    .filter((part) => /[a-z0-9]/i.test(part));
  if (!parts.length) return '·';
  return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join('');
}

export function count(value) {
  return Number(value || 0).toLocaleString();
}

export function debounce(fn, wait = 300) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

export function toast(message, kind = 'info') {
  const host = document.getElementById('toasts');
  if (!host) return;
  const glyph = kind === 'error' ? 'alert' : kind === 'success' ? 'check' : 'sparkles';
  const node = el(
    'div',
    { class: `toast ${kind} toast-enter` },
    icon(glyph, 'icon'),
    el('span', {}, message)
  );
  host.append(node);
  window.setTimeout(() => {
    node.style.transition = 'opacity .2s ease, transform .2s ease';
    node.style.opacity = '0';
    node.style.transform = 'translateY(4px)';
    window.setTimeout(() => node.remove(), 220);
  }, 4200);
}

export function openModal({ title, body, footer = [], wide = false }) {
  const modal = document.getElementById('modal');
  if (!modal) return { close: () => {} };
  modal.classList.toggle('wide', Boolean(wide));
  document.getElementById('modal-title').textContent = title;
  const bodyHost = document.getElementById('modal-body');
  const bodyNodes = Array.isArray(body) ? body : [body];
  bodyHost.replaceChildren(...bodyNodes.filter(Boolean));
  const footHost = document.getElementById('modal-foot');
  const footNodes = Array.isArray(footer) ? footer.filter(Boolean) : [footer].filter(Boolean);
  footHost.replaceChildren(...footNodes);
  modal.classList.toggle('no-foot', footNodes.length === 0);
  if (!modal.open) modal.showModal();
  return {
    close: () => modal.close(),
    setBusy: (busy) => {
      for (const button of footHost.querySelectorAll('button')) button.disabled = busy;
    },
  };
}

export function closeModal() {
  const modal = document.getElementById('modal');
  if (modal?.open) modal.close();
}

export function confirmDialog({ title, message, confirmLabel = 'Confirm', onConfirm }) {
  let busy = false;
  const confirm = el(
    'button',
    {
      class: 'btn btn-primary',
      type: 'button',
      onClick: async () => {
        if (busy) return;
        busy = true;
        confirm.disabled = true;
        try {
          await onConfirm();
          closeModal();
        } finally {
          busy = false;
          confirm.disabled = false;
        }
      },
    },
    confirmLabel
  );
  return openModal({
    title,
    body: el('p', { class: 'hint' }, message),
    footer: [
      el('button', { class: 'btn btn-ghost', type: 'button', onClick: closeModal }, 'Cancel'),
      confirm,
    ],
  });
}

export function proseNodes(text) {
  const fragment = document.createDocumentFragment();
  const blocks = String(text || '').replace(/\r\n/g, '\n').split(/\n{2,}/);
  for (const raw of blocks) {
    const block = raw.trim();
    if (!block) continue;
    if (/^###\s+/.test(block)) fragment.append(el('h3', {}, block.replace(/^###\s+/, '')));
    else if (/^##\s+/.test(block)) fragment.append(el('h2', {}, block.replace(/^##\s+/, '')));
    else if (/^#\s+/.test(block)) fragment.append(el('h1', {}, block.replace(/^#\s+/, '')));
    else if (block === '---' || block === '***') fragment.append(el('div', { class: 'rule' }));
    else fragment.append(el('p', {}, block.replace(/\n/g, ' ')));
  }
  if (!fragment.childNodes.length) {
    fragment.append(el('p', { class: 'reader-empty' }, 'This scene has no prose yet.'));
  }
  return fragment;
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard.', 'success');
  } catch (error) {
    toast('Clipboard access was refused by the browser.', 'error');
  }
}
