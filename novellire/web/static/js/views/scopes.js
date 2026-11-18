import { api } from '../api.js';
import {
  closeModal,
  el,
  emptyState,
  field,
  formatDate,
  icon,
  input,
  openModal,
  select,
  textarea,
  toast,
} from '../ui.js';

const CHAT_MODES = {
  plan: { label: 'Plan', hint: 'Decide what happens. Notes are kept.' },
  write: { label: 'Write', hint: 'Draft prose from fresh project context.' },
};
const NEW_THREAD_TITLE = 'New conversation';

export function renderChat(ctx) {
  const { state } = ctx;
  const project = state.tree?.project;
  const wrap = el('div', { class: 'view-inner' });

  if (!project) {
    wrap.append(
      el(
        'div',
        { class: 'page-head' },
        el('div', {}, el('h1', {}, 'Chat'), el('div', { class: 'sub' }, 'Select a project to start a conversation.'))
      ),
      emptyState({
        iconName: 'message',
        title: 'No project selected',
        body: 'Choose a project first. Conversations are stored per project and per chapter.',
      })
    );
    return wrap;
  }

  const historyList = el('div', { class: 'chat-thread-list' });
  const newThread = el(
    'button',
    { class: 'btn btn-block', type: 'button', onClick: () => openNewThread() },
    icon('plus'),
    'New conversation'
  );
  const history = el(
    'aside',
    { class: 'chat-history' },
    el('div', { class: 'history-title' }, 'Conversations'),
    newThread,
    historyList
  );

  const header = el('div', { class: 'chat-head' });
  const stream = el('div', { class: 'chat-stream' });
  const notesHost = el('div', { class: 'chat-notes-host' });
  const composerText = textarea({
    rows: 2,
    placeholder: 'Ask about canon, characters, or what happens next…',
  });
  const sendButton = el(
    'button',
    { class: 'btn btn-primary', type: 'button', onClick: () => send() },
    icon('sparkles'),
    'Send'
  );
  const stopButton = el(
    'button',
    { class: 'btn btn-ghost stop-btn', type: 'button', onClick: () => stop(), hidden: true },
    icon('x'),
    'Stop'
  );
  const composerNote = el(
    'div',
    { class: 'composer-note' },
    icon('alert', 'icon sm'),
    'Choose a conversation or start a new one.'
  );
  const composer = el(
    'div',
    { class: 'chat-composer' },
    el('div', { class: 'composer-row' }, composerText, stopButton, sendButton),
    composerNote
  );
  const main = el('div', { class: 'chat-main' }, header, stream, notesHost, composer);
  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, 'Chat'),
        el(
          'div',
          { class: 'sub' },
          'Chapter-scoped planning and drafting. Write mode rebuilds context from documents, notes, chapter, and memory.'
        )
      ),
      el('div', { class: 'actions' }, el('span', { class: 'chip accent' }, 'Project scoped'))
    )
  );
  wrap.append(el('div', { class: 'chat-shell' }, history, main));

  let threads = [];
  let active = null;
  let busy = false;
  let abortController = null;

  function chapterFor(thread) {
    if (!thread?.chapter_id) return null;
    return (state.manuscript?.chapters || []).find(
      (chapter) => chapter.id === thread.chapter_id
    ) || null;
  }

  function renderHistory() {
    historyList.replaceChildren();
    if (!threads.length) {
      historyList.append(el('p', { class: 'hint' }, 'No conversations yet.'));
      return;
    }
    for (const thread of threads) {
      const chapter = chapterFor(thread);
      historyList.append(
        el(
          'button',
          {
            class: `chat-thread ${active?.id === thread.id ? 'active' : ''}`,
            type: 'button',
            onClick: () => selectThread(thread.id),
          },
          el(
            'span',
            { class: 'chat-thread-title' },
            thread.title || NEW_THREAD_TITLE
          ),
          el(
            'span',
            { class: 'chat-thread-meta' },
            el('span', { class: `chip ${thread.mode === 'write' ? 'accent' : 'soon'}` }, CHAT_MODES[thread.mode]?.label || thread.mode),
            chapter ? `Chapter ${chapter.position}` : 'Project-wide',
            thread.message_count ? `· ${thread.message_count}` : ''
          )
        )
      );
    }
  }

  function renderHeader() {
    if (!active) {
      header.replaceChildren(
        el('strong', {}, project.name),
        el('span', { class: 'chip' }, 'No conversation')
      );
      return;
    }
    const chapter = chapterFor(active);
    header.replaceChildren(
      el(
        'div',
        { class: 'chat-head-title' },
        el('strong', {}, active.title || NEW_THREAD_TITLE),
        el(
          'span',
          { class: 'chat-head-meta' },
          chapter ? `Chapter ${chapter.position} — ${chapter.title}` : 'Project-wide',
          ' · ',
          formatDate(active.updated_at)
        )
      ),
      el(
        'span',
        { class: `chip ${active.mode === 'write' ? 'accent' : 'soon'}` },
        CHAT_MODES[active.mode]?.label || active.mode
      )
    );
  }

  function bubble(role, content, model = '') {
    return el(
      'div',
      { class: `chat-bubble ${role === 'user' ? 'user' : ''}` },
      el('span', { class: 'avatar' }, icon(role === 'user' ? 'user' : 'feather', 'icon sm')),
      el(
        'div',
        { class: 'bubble' },
        content,
        role === 'assistant' && model ? el('span', { class: 'bubble-model' }, model) : null
      )
    );
  }

  function streamingBubble() {
    const text = document.createTextNode('');
    const modelTag = el('span', { class: 'bubble-model' });
    const body = el('div', { class: 'bubble streaming' }, text, modelTag);
    const node = el(
      'div',
      { class: 'chat-bubble' },
      el('span', { class: 'avatar' }, icon('feather', 'icon sm')),
      body
    );
    return {
      node,
      append(chunk) {
        text.data += chunk;
      },
      finish(model) {
        body.classList.remove('streaming');
        if (model) modelTag.textContent = model;
      },
    };
  }

  function scrollStream() {
    stream.scrollTop = stream.scrollHeight;
  }

  function renderStream(messages) {
    stream.replaceChildren();
    if (!messages.length) {
      stream.append(
        emptyState({
          iconName: active?.mode === 'write' ? 'feather' : 'message',
          title: active?.mode === 'write' ? 'Draft from fresh context' : 'Plan the next move',
          body:
            active?.mode === 'write'
              ? 'Ask for a scene. Novellire reloads the documents, chapter, planning notes, and retrieved memory for each reply.'
              : 'Ask what should happen next. Decisions are saved as editable planning notes.',
        })
      );
      return;
    }
    for (const message of messages) {
      stream.append(bubble(message.role, message.content, message.model));
    }
    stream.scrollTop = stream.scrollHeight;
  }

  function renderNotes() {
    notesHost.replaceChildren();
    if (!active || active.mode !== 'plan') return;
    const notes = textarea({
      rows: 6,
      value: active.planning_notes || '',
      placeholder: 'Decisions, constraints, and unresolved questions for this chapter.',
    });
    const save = el(
      'button',
      { class: 'btn btn-ghost', type: 'button' },
      icon('check'),
      'Save notes'
    );
    save.addEventListener('click', async () => {
      save.disabled = true;
      try {
        active = await api.patch(`/api/chat/threads/${active.id}`, {
          planning_notes: notes.value,
        });
        const item = threads.find((thread) => thread.id === active.id);
        if (item) Object.assign(item, active);
        renderHeader();
        renderNotes();
        toast('Planning notes saved.', 'success');
      } catch (error) {
        toast(error.message, 'error');
        save.disabled = false;
      }
    });
    const source =
      active.planning_notes_source === 'author'
        ? 'Author-edited notes are locked against model replacement.'
        : active.planning_notes_source === 'model'
          ? 'Maintained from Plan replies until you edit them.'
          : 'Plan replies propose notes here.';
    notesHost.append(
      el(
        'details',
        { class: 'chat-notes', open: Boolean(active.planning_notes) },
        el(
          'summary',
          {},
          el('strong', {}, 'Planning notes'),
          el('span', { class: 'chip' }, active.planning_notes_source || 'empty')
        ),
        el('p', { class: 'hint' }, source),
        notes,
        el('div', { class: 'chat-notes-actions' }, save)
      )
    );
  }

  function renderComposer() {
    const enabled = Boolean(active) && !busy;
    composerText.disabled = !enabled;
    sendButton.disabled = !enabled;
    sendButton.hidden = busy;
    stopButton.hidden = !busy;
    stopButton.disabled = !busy;
    composerText.placeholder = active
      ? active.mode === 'write'
        ? 'Describe the scene to draft, or ask for a revision…'
        : 'Ask about canon, characters, or what happens next…'
      : 'Start a conversation first.';
    composerNote.replaceChildren(
      icon('alert', 'icon sm'),
      busy
        ? 'Generating… one local inference request is running. Stop keeps what arrived.'
        : active
          ? CHAT_MODES[active.mode]?.hint || ''
          : 'Choose a conversation or start a new one.'
    );
  }

  async function selectThread(threadId) {
    if (!threadId) {
      active = null;
      state.chatThreadId = null;
      renderHistory();
      renderHeader();
      renderStream([]);
      renderNotes();
      renderComposer();
      return;
    }
    try {
      const bundle = await api.get(`/api/chat/threads/${threadId}`);
      active = bundle.thread;
      state.chatThreadId = active.id;
      renderHistory();
      renderHeader();
      renderStream(bundle.messages);
      renderNotes();
      renderComposer();
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function loadThreads(preferredId = state.chatThreadId) {
    try {
      threads = await api.get(`/api/projects/${project.id}/chat/threads`);
      renderHistory();
      const target = threads.some((thread) => thread.id === preferredId)
        ? preferredId
        : threads[0]?.id || null;
      await selectThread(target);
    } catch (error) {
      toast(error.message, 'error');
      historyList.replaceChildren(el('p', { class: 'hint' }, error.message));
    }
  }

  function openNewThread() {
    const mode = select(
      [
        { value: 'plan', label: 'Plan — decide what happens' },
        { value: 'write', label: 'Write — draft prose' },
      ],
      { value: 'plan' }
    );
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
      'Start conversation'
    );
    const form = el(
      'form',
      { class: 'form-grid' },
      el('div', { class: 'span-2' }, field('Mode', mode, 'Plan keeps decisions; Write drafts prose.')),
      el('div', { class: 'span-2' }, field('Chapter', chapter, 'Chapter scope keeps retrieval before the selected chapter.')),
      el('div', { class: 'span-2' }, field('Title', title)),
      el('div', { class: 'form-actions span-2' }, submit)
    );
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const created = await api.post(`/api/projects/${project.id}/chat/threads`, {
          mode: mode.value,
          chapter_id: chapter.value ? Number(chapter.value) : null,
          title: title.value.trim(),
        });
        closeModal();
        await loadThreads(created.id);
        toast('Conversation started.', 'success');
      } catch (error) {
        toast(error.message, 'error');
        submit.disabled = false;
      }
    });
    openModal({ title: 'New conversation', body: form });
  }

  async function refreshThreads() {
    try {
      threads = await api.get(`/api/projects/${project.id}/chat/threads`);
      renderHistory();
    } catch (error) {
      /* keep the list already on screen */
    }
  }

  function stop() {
    abortController?.abort();
  }

  async function send() {
    if (busy || !active) return;
    const text = composerText.value.trim();
    if (!text) {
      toast('Write a message before sending.', 'error');
      return;
    }
    const settings = state.settings?.generation || {};
    const model = settings.model || state.ollama?.models?.[0]?.name || '';
    if (!model) {
      toast('Choose a model in Settings first.', 'error');
      return;
    }
    busy = true;
    const threadId = active.id;
    const reply = streamingBubble();
    renderComposer();
    stream.append(bubble('user', text));
    stream.append(reply.node);
    scrollStream();
    composerText.value = '';
    abortController = new AbortController();
    let failure = '';
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
            reply.append(event.text || '');
            scrollStream();
          } else if (event.type === 'done') {
            reply.finish(event.assistant?.model || model);
            active = event.thread;
            state.chatThreadId = active.id;
            const item = threads.find((thread) => thread.id === active.id);
            if (item) Object.assign(item, active);
            renderHistory();
            renderHeader();
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
        // The server stores the partial reply before the stream closes.
        await new Promise((resolve) => setTimeout(resolve, 300));
        await refreshThreads();
        await selectThread(threadId);
      } else {
        toast(error.message, 'error');
        await selectThread(threadId);
      }
    } finally {
      abortController = null;
      busy = false;
      renderComposer();
    }
  }

  loadThreads();
  return wrap;
}

const SCOPES = {
  continuity: {
    title: 'Continuity',
    icon: 'shield',
    phase: 'Phase 5',
    subtitle:
      'A review surface for contradictions the harness finds between generated prose and established canon.',
    cards: [
      { title: 'Timeline conflicts', body: 'Events that cannot occur in the recorded order.' },
      { title: 'Character knowledge', body: 'A character acting on information they never learned.' },
      { title: 'Canon conflicts', body: 'Prose contradicting an approved story bible entry.' },
      { title: 'Unresolved threads', body: 'Planted mysteries and promises still waiting to pay off.' },
    ],
  },
};

export function renderScope(ctx, key) {
  const scope = SCOPES[key] || SCOPES.continuity;
  const wrap = el('div', { class: 'view-inner' });

  wrap.append(
    el(
      'div',
      { class: 'page-head' },
      el(
        'div',
        {},
        el('h1', {}, scope.title),
        el('div', { class: 'sub' }, scope.subtitle)
      ),
      el('div', { class: 'actions' }, el('span', { class: 'chip soon' }, scope.phase))
    )
  );

  wrap.append(
    el(
      'div',
      { class: 'card card-pad', style: { marginBottom: '18px', display: 'flex', gap: '12px', alignItems: 'flex-start' } },
      icon('alert'),
      el(
        'div',
        {},
        el('strong', { style: { fontSize: 'var(--fs-sm)' } }, 'This surface is a layout scope'),
        el(
          'p',
          { class: 'hint', style: { marginTop: '4px' } },
          'The panels, filters, and detail views are reserved so the backend feature can be connected without redesigning the interface. No data is displayed yet.'
        )
      )
    )
  );

  const grid = el('div', { class: 'scope-grid' });
  for (const card of scope.cards) {
    grid.append(
      el(
        'div',
        { class: 'card scope-card' },
        el('div', { class: 'scope-head' }, icon(scope.icon), el('strong', {}, card.title)),
        el('p', { class: 'hint' }, card.body),
        el(
          'div',
          { class: 'lines', 'aria-hidden': 'true' },
          el('div', { class: 'skeleton' }),
          el('div', { class: 'skeleton' }),
          el('div', { class: 'skeleton' })
        ),
        el('div', { class: 'foot' }, icon('clock', 'icon sm'), `Wired in ${scope.phase}`)
      )
    );
  }

  const tree = ctx.state.tree;
  if (tree) {
    wrap.append(
      el(
        'p',
        { class: 'hint', style: { marginTop: '16px' } },
        `Project “${tree.project.name}” already has ${tree.stats.chapters} chapters and ${tree.stats.words.toLocaleString()} words ready for this surface to read.`
      )
    );
  }

  wrap.append(grid);
  return wrap;
}
