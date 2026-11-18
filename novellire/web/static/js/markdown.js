/* Minimal markdown renderer for model replies.
 *
 * It builds DOM nodes and never assigns HTML, so generated text cannot inject
 * markup. Supported syntax: fenced code, headings, lists, blockquotes, rules,
 * bold, italic, inline code, and http(s) links.
 */

const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;

function inline(text) {
  const frag = document.createDocumentFragment();
  let index = 0;
  for (const match of String(text).matchAll(INLINE)) {
    if (match.index > index) {
      frag.append(document.createTextNode(text.slice(index, match.index)));
    }
    const [raw, code, bold, italic, label, href] = match;
    if (code) {
      const node = document.createElement('code');
      node.textContent = code.slice(1, -1);
      frag.append(node);
    } else if (bold) {
      const node = document.createElement('strong');
      node.append(inline(bold.slice(2, -2)));
      frag.append(node);
    } else if (italic) {
      const node = document.createElement('em');
      node.append(inline(italic.slice(1, -1)));
      frag.append(node);
    } else {
      const link = document.createElement('a');
      link.href = href;
      link.textContent = label;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      frag.append(link);
    }
    index = match.index + raw.length;
  }
  if (index < text.length) frag.append(document.createTextNode(text.slice(index)));
  return frag;
}

function codeBlock(code, language) {
  const figure = document.createElement('figure');
  figure.className = 'md-code';

  const head = document.createElement('div');
  head.className = 'md-code-head';
  const label = document.createElement('span');
  label.textContent = language || 'text';
  const copy = document.createElement('button');
  copy.type = 'button';
  copy.className = 'md-copy';
  copy.textContent = 'Copy';
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(code);
      copy.textContent = 'Copied';
    } catch (error) {
      copy.textContent = 'Copy failed';
    }
    window.setTimeout(() => { copy.textContent = 'Copy'; }, 1600);
  });
  head.append(label, copy);

  const pre = document.createElement('pre');
  const body = document.createElement('code');
  body.textContent = code;
  pre.append(body);
  figure.append(head, pre);
  return figure;
}

function listBlock(lines, start) {
  const ordered = /^\s*\d+[.)]\s+/.test(lines[start]);
  const list = document.createElement(ordered ? 'ol' : 'ul');
  const pattern = ordered ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
  let index = start;
  while (index < lines.length) {
    const item = lines[index].match(pattern);
    if (!item) break;
    const node = document.createElement('li');
    node.append(inline(item[1]));
    list.append(node);
    index += 1;
  }
  return { list, next: index };
}

export function renderMarkdown(source) {
  const frag = document.createDocumentFragment();
  const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
  let paragraph = [];
  let index = 0;

  const flush = () => {
    if (!paragraph.length) return;
    const block = document.createElement('p');
    paragraph.forEach((line, position) => {
      if (position) block.append(document.createElement('br'));
      block.append(inline(line));
    });
    frag.append(block);
    paragraph = [];
  };

  while (index < lines.length) {
    const line = lines[index];

    const fence = line.match(/^\s*```([\w+-]*)\s*$/);
    if (fence) {
      flush();
      index += 1;
      const body = [];
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1;
      frag.append(codeBlock(body.join('\n'), fence[1]));
      continue;
    }

    if (!line.trim()) {
      flush();
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flush();
      const node = document.createElement(`h${Math.min(heading[1].length + 1, 4)}`);
      node.append(inline(heading[2]));
      frag.append(node);
      index += 1;
      continue;
    }

    if (/^\s*(?:-{3,}|\*{3,})\s*$/.test(line)) {
      flush();
      frag.append(document.createElement('hr'));
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flush();
      const quote = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ''));
        index += 1;
      }
      const node = document.createElement('blockquote');
      node.append(renderMarkdown(quote.join('\n')));
      frag.append(node);
      continue;
    }

    if (/^\s*(?:[-*+]|\d+[.)])\s+/.test(line)) {
      flush();
      const { list, next } = listBlock(lines, index);
      frag.append(list);
      index = next;
      continue;
    }

    paragraph.push(line);
    index += 1;
  }

  flush();
  return frag;
}
