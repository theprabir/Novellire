import { api } from '../api.js';
import { renderMarkdown } from '../markdown.js';
import {
  closeModal,
  el,
  formatDate,
  icon,
  input,
  openModal,
  select,
  toast,
} from '../ui.js';

const MODES = [
  { value: 'write', label: 'Write' },
  { value: 'plan', label: 'Plan' },
];
const NEW_THREAD_TITLE = 'New conversation';
const DRAFT_KEY = 'novellire.chat.draft';

function chapterFor(state, thread) {
  if (!thread?.chapter_id) return null;
  return (state.manuscript?.chapters || []).find(
    (chapter) => chapter.id === thread.chapter_id
  ) || null;
}

export function renderChat(ctx) {
  const { state } = ctx;
  const project = state.tree?.project;
  const root = el('div', { class: 'chat-app' });

  if (!project) {
    root.append(
      el(
        'div',
        { class: 'chat-blank' },
        icon('message', 'icon lg'),
        el('h2', {}, 'No project selected'),
        el('p', {}, 'Choose a project in the sidebar to start a conversation.')
      )
    );
    return root;
  }

  /* -- conversation drawer -------------------------------------------- */

  const drawerList = el('div', { class: 'chat-drawer-list' });
  const drawer = el(
    'aside',
    { class: 'chat-drawer', 'aria-label': 'Conversations' },
    el(
      'div',
      { class: 'chat-drawer-head' },
      el('strong', {}, 'Conversations'),
      el(
        'button',
        {
          class: 'icon-btn',
          type: 'button',
          title: 'Close conversations',
          'aria-label': 'Close conversations',
          onClick: () => toggleDrawer(false),
        },
        icon('x')
      )
    ),
    el(
      'button',
      { class: 'chat-new', type: 'button', onClick: () => openNewThread() },
      icon('plus'),
      'New chat'
    ),
    drawerList
  );
  const scrim = el('div', {
    class: 'chat-scrim',
    hidden: true,
    onClick: () => toggleDrawer(false),
  });

  /* -- header ---------------------------------------------------------- */

  const titleNode = el('strong', { class: 'chat-title' }, 'New chat');
  const subtitleNode = el('span', { class: 'chat-subtitle' }, project.name);
  const notesButton = el(
    'button',
    {
      class: 'icon-btn',
      type: 'button',
      title: 'Planning notes',
      'aria-label': 'Planning notes',
      hidden: true,
      onClick: () => toggleNotes(),
    },
    icon('pencil')
  );
  const header = el(
    'header',
    { class: 'chat-header' },
    el(
      'button',
      {
        class: 'icon-btn',
        type: 'button',
        title: 'Conversations',
        'aria-label': 'Conversations',
        onClick: () => toggleDrawer(),
      },
      icon('sidebar')
    ),
    el('div', { class: 'chat-heading' }, titleNode, subtitleNode),
    el(
      'div',
      { class: 'chat-header-actions' },
      notesButton,
      el(
        'button',
        {
          class: 'icon-btn',
          type: 'button',
          title: 'New chat',
          'aria-label': 'New chat',
          onClick: () => openNewThread(),
        },
        icon('plus')
      )
    )
  );

  /* -- message feed ---------------------------------------------------- */

  const feed = el('div', { class: 'chat-feed', role: 'log', 'aria-live': 'polite' });
  const scroll = el(
    'div',
    { class: 'chat-scroll' },
    feed
  );

  /* -- planning notes -------------------------------------------------- */

  const notesSource = el('span', { class: 'chat-notes-source' });
  const notesText = el('textarea', {
    class: 'chat-notes-input',
    rows: 5,
    placeholder: 'Decisions, constraints, and unresolved questions for this chapter.',
  });
  const notesSave = el(
    'button',
    { class: 'btn btn-primary btn-sm', type: 'button', onClick: () => saveNotes() },
    icon('check'),
    'Save notes'
  );
  const notesPanel = el(
    'section',
    { class: 'chat-notes', hidden: true, 'aria-label': 'Planning notes' },
    el('div', { class: 'chat-notes-head' }, el('strong', {}, 'Planning notes'), notesSource),
    notesText,
    el('div', { class: 'chat-notes-actions' }, notesSave)
  );

  /* -- composer -------------------------------------------------------- */

  const inputBox = el('textarea', {
    class: 'chat-input',
    rows: 1,
    placeholder: 'Message Novellire…',
    'aria-label': 'Message Novellire',
  });
  const modeSwitch = el('div', { class: 'chat-mode', role: 'group', 'aria-label': 'Reply mode' });
  const modeButtons = new Map();
  for (const mode of MODES) {
    const button = el(
      'button',
      {
        class: 'chat-mode-btn',
        type: 'button',
        'aria-pressed': 'false',
        onClick: () => setMode(mode.value),
      },
      mode.label
    );
    modeButtons.set(mode.value, button);
    modeSwitch.append(button);
  }
  const actionButton = el(
    'button',
    { class: 'chat-send', type: 'button', title: 'Send message', 'aria-label': 'Send message' },
    icon('arrow-up')
  );
  const dockHint = el('span', { class: 'chat-dock-hint' });
  const form = el(
    'form',
    { class: 'chat-composer' },
    inputBox,
    el(
      'div',
      { class: 'chat-composer-bar' },
      modeSwitch,
      el('div', { class: 'chat-composer-right' }, dockHint, actionButton)
    )
  );
  const dock = el(
    'div',
    { class: 'chat-dock' },
    el(
      'div',
      { class: 'chat-dock-inner' },
      notesPanel,
      form,
      el(
        'p',
        { class: 'chat-disclaimer' },
        'Novellire writes with your local model. Enter sends, Shift + Enter adds a line.'
      )
    )
  );

  const column = el('div', { class: 'chat-column' }, scroll, dock);
  root.append(header, el('div', { class: 'chat-body' }, drawer, scrim, column));

  /* -- state ----------------------------------------------------------- */

  let threads = [];
  let active = null;
  let pendingMode = 'plan';
  let busy = false;
  let notesOpen = false;
  let abortController = null;
  let pinned = true;

  scroll.addEventListener('scroll', () => {
    pinned = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 120;
  });

  actionButton.addEventListener('click', () => {
    if (busy) stop();
    else form.requestSubmit();
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    send();
  });

  inputBox.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!busy) send();
    }
  });

  inputBox.addEventListener('input', () => {
    autoGrow();
    renderComposer();
    saveDraft();
  });

  try {
    const saved = window.localStorage.getItem(DRAFT_KEY);
    if (saved) inputBox.value = saved;
  } catch (error) { /* drafts are optional */ }

  root.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && root.classList.contains('drawer-open')) {
      toggleDrawer(false);
    }
  });

  /* -- rendering ------------------------------------------------------- */

  function renderDrawer() {
    drawerList.replaceChildren();
    if (!threads.length) {
      drawerList.append(el('p', { class: 'chat-drawer-empty' }, 'No conversations yet.'));
      return;
    }
    for (const thread of threads) {
      const chapter = chapterFor(state, thread);
      drawerList.append(
        el(
          'button',
          {
            class: `chat-thread ${active?.id === thread.id ? 'active' : ''}`,
            type: 'button',
            onClick: () => selectThread(thread.id),
          },
          el('span', { class: 'chat-thread-title' }, thread.title || NEW_THREAD_TITLE),
          el(
            'span',
            { class: 'chat-thread-meta' },
            el('span', { class: `chat-thread-mode ${thread.mode}` }, thread.mode),
            chapter ? `Chapter ${chapter.position}` : 'Project-wide',
            formatDate(thread.updated_at)
          )
        )
      );
    }
  }

  function renderHeader() {
    const chapter = active ? chapterFor(state, active) : null;
    titleNode.textContent = active ? active.title || NEW_THREAD_TITLE : 'New chat';
    const scope = active
      ? chapter
        ? `Chapter ${chapter.position} — ${chapter.title}`
        : 'Project-wide'
      : project.name;
    subtitleNode.textContent = `${scope} · ${modeLabel()}`;
    notesButton.hidden = !(active && active.mode === 'plan');
  }

  function renderMode() {
    const current = active?.mode || pendingMode;
    for (const [value, button] of modeButtons) {
      const pressed = value === current;
      button.classList.toggle('active', pressed);
      button.setAttribute('aria-pressed', pressed ? 'true' : 'false');
      button.disabled = busy;
    }
    modeSwitch.title = current === 'write'
      ? 'Write drafts prose from fresh project context'
      : 'Plan decides what happens; notes are kept';
  }

  function renderComposer() {
    const generating = busy;
    actionButton.replaceChildren(icon(generating ? 'square' : 'arrow-up'));
    actionButton.classList.toggle('is-stop', generating);
    const label = generating ? 'Stop generating' : 'Send message';
    actionButton.title = label;
    actionButton.setAttribute('aria-label', label);
    actionButton.disabled = !generating && !inputBox.value.trim();
    dockHint.textContent = generating ? 'Generating…' : '';
    inputBox.placeholder = active
      ? active.mode === 'write'
        ? 'Describe the scene to draft, or ask for a revision…'
        : 'Ask about canon, characters, or what happens next…'
      : 'Message Novellire…';
  }

  function renderNotes() {
    notesPanel.hidden = !notesOpen;
    notesButton.classList.toggle('active', notesOpen);
    if (!active) return;
    notesText.value = active.planning_notes || '';
    notesSource.textContent =
      active.planning_notes_source === 'author'
        ? 'author'
        : active.planning_notes_source === 'model'
          ? 'model'
          : 'empty';
  }

  function autoGrow() {
    inputBox.style.height = 'auto';
    inputBox.style.height = `${Math.min(inputBox.scrollHeight, 220)}px`;
  }

  function messageNode(message) {
    if (message.role === 'user') {
      return el(
        'article',
        { class: 'msg msg-user' },
        el('div', { class: 'msg-bubble' }, message.content)
      );
    }
    const body = el('div', { class: 'msg-body md' });
    body.append(renderMarkdown(message.content));
    return el(
      'article',
      { class: 'msg msg-assistant' },
      body,
      message.model ? el('div', { class: 'msg-meta' }, message.model) : null
    );
  }

  function streamingMessage() {
    const text = document.createTextNode('');
    const body = el('div', { class: 'msg-body md streaming' }, text);
    const meta = el('div', { class: 'msg-meta' });
    const node = el('article', { class: 'msg msg-assistant' }, body, meta);
    return {
      node,
      append(chunk) {
        text.data += chunk;
      },
      finish(model, content) {
        body.classList.remove('streaming');
        body.replaceChildren(renderMarkdown(content));
        meta.textContent = model || '';
      },
    };
  }

  function welcome() {
    const writing = (active?.mode || pendingMode) === 'write';
    return el(
      'div',
      { class: 'chat-welcome' },
      el('div', { class: 'chat-welcome-mark' }, icon('feather', 'icon lg')),
      el('h2', {}, writing ? 'Draft the next passage' : 'Plan the next move'),
      el(
        'p',
        {},
        writing
          ? 'Describe the scene you want. Every reply rebuilds its context from the documents, planning notes, chapter, and memory.'
          : 'Ask what should happen next. Decisions are kept as editable planning notes.'
      )
    );
  }

  function renderMessages(messages) {
    feed.replaceChildren();
    if (!messages.length) {
      feed.append(welcome());
      return;
    }
    for (const message of messages) feed.append(messageNode(message));
    scrollToEnd(true);
  }

  function scrollToEnd(force = false) {
    if (force) pinned = true;
    if (pinned) scroll.scrollTop = scroll.scrollHeight;
  }

  function clearWelcome() {
    feed.querySelector('.chat-welcome')?.remove();
  }

  function modeLabel() {
    return (active?.mode || pendingMode) === 'write' ? 'Write' : 'Plan';
  }

  function saveDraft() {
    try {
      if (inputBox.value) window.localStorage.setItem(DRAFT_KEY, inputBox.value);
      else window.localStorage.removeItem(DRAFT_KEY);
    } catch (error) { /* drafts are optional */ }
  }

  /* -- actions --------------------------------------------------------- */

  function toggleDrawer(open) {
    const next = typeof open === 'boolean' ? open : !root.classList.contains('drawer-open');
    root.classList.toggle('drawer-open', next);
    scrim.hidden = !next;
  }

  function toggleNotes() {
    if (!active || active.mode !== 'plan') return;
    notesOpen = !notesOpen;
    renderNotes();
    if (notesOpen) notesText.focus();
  }

  async function saveNotes() {
    if (!active) return;
    notesSave.disabled = true;
    try {
      active = await api.patch(`/api/chat/threads/${active.id}`, {
        planning_notes: notesText.value,
      });
      const item = threads.find((thread) => thread.id === active.id);
      if (item) Object.assign(item, active);
      renderNotes();
      renderDrawer();
      toast('Planning notes saved.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      notesSave.disabled = false;
    }
  }

  async function setMode(mode) {
    if (busy || mode === (active?.mode || pendingMode)) return;
    pendingMode = mode;
    if (!active) {
      renderMode();
      renderHeader();
      if (!feed.querySelector('.msg')) renderMessages([]);
      return;
    }
    const previous = active.mode;
    active = { ...active, mode };
    if (mode !== 'plan') {
      notesOpen = false;
      renderNotes();
    }
    renderMode();
    renderHeader();
    try {
      const updated = await api.patch(`/api/chat/threads/${active.id}`, { mode });
      active = updated;
      pendingMode = updated.mode;
      const item = threads.find((thread) => thread.id === active.id);
      if (item) Object.assign(item, updated);
      renderHeader();
      renderMode();
      renderDrawer();
    } catch (error) {
      active = { ...active, mode: previous };
      pendingMode = previous;
      renderMode();
      renderHeader();
      toast(error.message, 'error');
    }
  }

  async function selectThread(threadId) {
    if (busy) {
      toast('Wait for the current reply to finish, or stop it.', 'error');
      return;
    }
    try {
      const bundle = await api.get(`/api/chat/threads/${threadId}`);
      active = bundle.thread;
      state.chatThreadId = active.id;
      pendingMode = active.mode;
      notesOpen = false;
      renderHeader();
      renderDrawer();
      renderMode();
      renderMessages(bundle.messages);
      renderNotes();
      renderComposer();
      toggleDrawer(false);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function refreshThreads() {
    try {
      threads = await api.get(`/api/projects/${project.id}/chat/threads`);
      renderDrawer();
    } catch (error) {
      /* keep the list already on screen */
    }
  }

  async function reloadThread() {
    if (!active) return;
    try {
      const bundle = await api.get(`/api/chat/threads/${active.id}`);
      active = bundle.thread;
      pendingMode = active.mode;
      renderHeader();
      renderMode();
      renderMessages(bundle.messages);
      renderNotes();
    } catch (error) {
      /* the next page load will recover the conversation */
    }
  }

  async function loadThreads() {
    try {
      threads = await api.get(`/api/projects/${project.id}/chat/threads`);
      renderDrawer();
      const target = threads.find((thread) => thread.id === state.chatThreadId)
        || threads[0];
      if (target) {
        await selectThread(target.id);
      } else {
        active = null;
        renderHeader();
        renderMode();
        renderMessages([]);
        renderComposer();
      }
    } catch (error) {
      toast(error.message, 'error');
      drawerList.replaceChildren(el('p', { class: 'chat-drawer-empty' }, error.message));
    }
  }

  function openNewThread() {
    if (busy) {
      toast('Wait for the current reply to finish, or stop it.', 'error');
      return;
    }
    const chapters = state.manuscript?.chapters || [];
    const chapter = select(
      [
        { value: '', label: 'Project-wide' },
        ...chapters.map((item) => ({
          value: String(item.id),
          label: `Chapter ${item.position} — ${item.title}`,
        })),
      ],
      { value: '' }
    );
    const title = input({ placeholder: 'Optional title' });
    const submit = el(
      'button',
      { class: 'btn btn-primary', type: 'submit' },
      icon('plus'),
      'Start chat'
    );
    const formNode = el(
      'form',
      { class: 'form-grid' },
      el(
        'div',
        { class: 'span-2' },
        el('div', { class: 'field' }, el('label', { class: 'label' }, 'Chapter'), chapter,
          el('div', { class: 'hint' }, 'Chapter scope keeps retrieval before the selected chapter. The mode is chosen in the chat box.'))
      ),
      el('div', { class: 'span-2' }, el('div', { class: 'field' }, el('label', { class: 'label' }, 'Title'), title)),
      el('div', { class: 'form-actions span-2' }, submit)
    );
    formNode.addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const created = await api.post(`/api/projects/${project.id}/chat/threads`, {
          mode: pendingMode,
          chapter_id: chapter.value ? Number(chapter.value) : null,
          title: title.value.trim(),
        });
        closeModal();
        active = created;
        state.chatThreadId = created.id;
        threads = [created, ...threads];
        notesOpen = false;
        inputBox.value = '';
        autoGrow();
        renderHeader();
        renderDrawer();
        renderMode();
        renderMessages([]);
        renderNotes();
        renderComposer();
        toggleDrawer(false);
        inputBox.focus();
      } catch (error) {
        toast(error.message, 'error');
        submit.disabled = false;
      }
    });
    openModal({ title: 'New chat', body: formNode });
  }

  function stop() {
    abortController?.abort();
  }

  async function send() {
    if (busy) return;
    const text = inputBox.value.trim();
    if (!text) return;
    const settings = state.settings?.generation || {};
    const model = settings.model || state.ollama?.models?.[0]?.name || '';
    if (!model) {
      toast('Choose a model in Settings first.', 'error');
      return;
    }

    if (!active) {
      try {
        const created = await api.post(`/api/projects/${project.id}/chat/threads`, {
          mode: pendingMode,
          chapter_id: null,
          title: '',
        });
        active = created;
        state.chatThreadId = created.id;
        threads = [created, ...threads];
        renderHeader();
        renderDrawer();
        renderMode();
      } catch (error) {
        toast(error.message, 'error');
        return;
      }
    }

    busy = true;
    const threadId = active.id;
    const reply = streamingMessage();
    renderComposer();
    renderMode();
    clearWelcome();
    feed.append(messageNode({ role: 'user', content: text }), reply.node);
    scrollToEnd(true);
    inputBox.value = '';
    autoGrow();
    saveDraft();
    abortController = new AbortController();
    let failure = '';
    let collected = '';

    try {
      await api.stream(
        `/api/chat/threads/${threadId}/messages/stream`,
        {
          instructions: text,
          model,
          temperature: Number(settings.temperature ?? 0.7),
          top_p: Number(settings.top_p ?? 0.9),
          num_predict: Number(settings.num_predict ?? 700),
          context_window: Number(settings.context_window ?? 4096),
        },
        (event) => {
          if (event.type === 'delta') {
            collected += event.text || '';
            reply.append(event.text || '');
            scrollToEnd();
          } else if (event.type === 'done') {
            reply.finish(event.assistant?.model || model, collected);
            active = event.thread;
            state.chatThreadId = active.id;
            pendingMode = active.mode;
            const item = threads.find((thread) => thread.id === active.id);
            if (item) Object.assign(item, active);
            renderHeader();
            renderDrawer();
            renderNotes();
          } else if (event.type === 'error') {
            failure = event.message || 'The model did not finish the reply.';
          }
        },
        { signal: abortController.signal }
      );
      if (failure) throw new Error(failure);
      await refreshThreads();
    } catch (error) {
      if (error?.name === 'AbortError') {
        // The server stores the text received so far before the stream closes.
        await new Promise((resolve) => window.setTimeout(resolve, 300));
        await refreshThreads();
        await reloadThread();
      } else {
        toast(error.message, 'error');
        await reloadThread();
      }
    } finally {
      abortController = null;
      busy = false;
      renderComposer();
      renderMode();
      inputBox.focus();
    }
  }

  renderMode();
  renderComposer();
  loadThreads();
  window.requestAnimationFrame(() => {
    autoGrow();
    inputBox.focus();
  });
  return root;
}
