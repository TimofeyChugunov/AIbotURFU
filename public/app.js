'use strict';
const $ = (selector) => document.querySelector(selector);
const labels = {explain: 'Объяснить тему', report: 'Помочь с отчётом', presentation: 'Подготовить презентацию'};
const examples = {
  explain: ['Что такое искусственный интеллект?', 'Чем ИИ отличается от машинного обучения?', 'Объясни производную на примере'],
  report: ['Как составить введение по ГОСТу? Дай пару советов', 'Как написать выводы к лабораторной?', 'Составь план отчёта по практике'],
  presentation: ['План презентации об ИИ', 'Как рассказать о своём проекте?', 'Структура защиты курсовой'],
};
let storageKey = 'aiboturfu.chats.v1';
let chats = [];
let currentUser = null;
let identityResolved = false;
let accountEpoch = 0;
let current = null;
let mode = 'explain';
let busy = false;
let materials = [];
let connected = false;
let ready = false;

function applyUser(user) {
  const changed = !identityResolved || (currentUser?.id || null) !== (user?.id || null);
  currentUser = user || null;
  $('#profile-username').textContent = currentUser ? currentUser.username : 'Гость';
  $('#profile-detail').textContent = currentUser ? 'Личный аккаунт' : 'Без аккаунта';
  $('#user-avatar').textContent = currentUser ? currentUser.username[0].toUpperCase() : 'Г';
  $('#account-link').textContent = currentUser ? 'Аккаунт' : 'Вход / Регистрация';
  $('#user-logout').hidden = !currentUser;
  if (!changed) return;
  accountEpoch++;
  if (identityResolved) $('#prompt').value = '';
  identityResolved = true;
  storageKey = currentUser ? `aiboturfu.chats.user.${currentUser.id}.v1` : 'aiboturfu.chats.v1';
  chats = [];
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(parsed)) chats = parsed.filter(c => c && typeof c.id === 'string' && typeof c.title === 'string' && c.mode in labels && Array.isArray(c.messages) && c.messages.every(m => m && ['user', 'assistant'].includes(m.role) && typeof m.text === 'string')).slice(0, 30);
  } catch { /* History stays in memory if storage is unavailable. */ }
  current = null; setMode('explain'); renderHistory(); renderMessages();
}
async function syncAccount() {
  try { const result = await api('/api/auth/me'); applyUser(result.user); }
  catch { /* The normal server status displays connection failures. */ }
}
$('#user-logout').addEventListener('click', async () => {
  if (busy) return;
  $('#user-logout').disabled = true;
  try {
    await api('/api/auth/logout', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
    applyUser(null);
    try { localStorage.setItem('aiboturfu.auth.changed', crypto.randomUUID()); } catch { /* No token is stored here. */ }
  } catch (error) { $('#disclaimer').textContent = error.message; }
  finally { $('#user-logout').disabled = false; }
});
window.addEventListener('storage', event => { if (event.key === 'aiboturfu.auth.changed') syncAccount(); });

function save() {
  if (!identityResolved) return;
  try { localStorage.setItem(storageKey, JSON.stringify(chats.slice(0, 30))); }
  catch { $('#disclaimer').textContent = 'Не удалось сохранить историю в браузере. Текущий диалог доступен до закрытия страницы.'; }
}
function setMode(value) {
  mode = value;
  $('#mode-select').value = value;
  $('#current-mode').textContent = labels[value];
  document.querySelectorAll('[data-mode]').forEach(el => {
    const active = el.dataset.mode === value;
    el.classList.toggle('selected', active);
    el.setAttribute('aria-pressed', String(active));
  });
  $('#suggestions').replaceChildren();
  examples[value].forEach(text => {
    const button = document.createElement('button');
    button.textContent = text + ' ↗';
    button.addEventListener('click', () => { $('#prompt').value = text; $('#prompt').focus(); });
    $('#suggestions').append(button);
  });
  if (current && !busy) { current.mode = mode; save(); }
}
function renderHistory() {
  const list = $('#history');
  list.replaceChildren();
  if (!chats.length) {
    const note = document.createElement('p');
    note.className = 'empty-history';
    note.textContent = 'Здесь появятся твои диалоги';
    list.append(note);
  }
  chats.forEach(chat => {
    const button = document.createElement('button');
    button.textContent = chat.title;
    button.title = chat.title;
    button.addEventListener('click', () => {
      if (busy) return;
      current = chat;
      setMode(chat.mode);
      renderMessages();
      closeMenu();
    });
    list.append(button);
  });
}
function appendMessage(message) {
  const article = document.createElement('article');
  article.className = 'message ' + message.role;
  if (message.role === 'assistant') {
    const label = document.createElement('div');
    label.className = 'message-label';
    const icon = document.createElement('span');
    icon.className = 'mini-logo'; icon.textContent = 'ai';
    label.append(icon, document.createTextNode(message.demo ? 'AIbotURFU · ДЕМО' : 'AIbotURFU'));
    article.append(label);
  }
  const text = document.createElement('div');
  text.className = 'message-text'; text.textContent = message.text;
  article.append(text);
  if (Array.isArray(message.sources) && message.sources.length) {
    const sources = document.createElement('div'); sources.className = 'sources';
    const heading = document.createElement('div');
    heading.textContent = message.demo ? 'Найдено локальным поиском:' : 'Материалы, переданные ИИ (проверь подтверждение ответа):';
    sources.append(heading);
    message.sources.forEach((source, index) => {
      const details = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = `[${index + 1}] ${source.name}`;
      details.append(summary);
      if (typeof source.excerpt === 'string') {
        const quote = document.createElement('blockquote'); quote.textContent = source.excerpt; details.append(quote);
      }
      if (typeof source.id === 'string' && /^[a-f0-9]{24}$/.test(source.id)) {
        const link = document.createElement('a'); link.textContent = 'Открыть документ ↗';
        link.href = `/api/materials/${source.id}/view`; link.target = '_blank'; link.rel = 'noopener';
        details.append(link);
      }
      sources.append(details);
    });
    article.append(sources);
  }
  $('#messages').append(article);
}
function renderMessages() {
  $('#messages').replaceChildren();
  $('#welcome').hidden = !!current?.messages.length;
  current?.messages.forEach(appendMessage);
  scrollToEnd();
}
function scrollToEnd() { requestAnimationFrame(() => { $('#chat-area').scrollTop = $('#chat-area').scrollHeight; }); }
function closeMenu() { $('#sidebar').classList.remove('open'); $('#menu').setAttribute('aria-expanded', 'false'); }

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, signal: AbortSignal.timeout(path === '/api/chat' ? 195000 : 10000) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Не удалось выполнить запрос.');
  return result;
}
async function refreshStatus() {
  try {
    const status = await api('/api/status');
    applyUser(status.user);
    connected = true;
    ready = status.ready;
    $('#mode-status').textContent = status.demo ? '◉ Деморежим' : status.provider === 'ollama' ? (ready ? '◉ Qwen · локально' : 'Ollama недоступна') : ready ? '◉ Режим ИИ' : 'ИИ не настроен';
    $('#mode-status').classList.toggle('live', !status.demo && status.ready);
    $('#disclaimer').textContent = status.demo
      ? 'Деморежим · Локальный поиск и шаблоны без ИИ. Выдержки из документов можно проверить в источниках.'
      : status.provider === 'ollama'
        ? (ready ? 'Qwen3 · ИИ работает на этом компьютере. Материалы не отправляются в облако. Проверяй важные факты.' : status.error || 'Запусти Ollama, затем скачай qwen3:8b и обнови страницу.')
        : 'Вопрос, последние сообщения и найденные фрагменты материалов отправляются OpenAI. Проверяй важные факты.';
    $('#send').disabled = !status.ready;
  } catch {
    connected = false;
    ready = false;
    $('#send').disabled = true;
    $('#mode-status').textContent = 'Сервер недоступен';
    $('#disclaimer').textContent = 'Не удалось связаться с сервером. Проверь запуск приложения и обнови страницу.';
  }
}
async function loadMaterials() {
  try {
    materials = await api('/api/materials');
    $('#material-count').textContent = materials.length;
    $('#material-list').replaceChildren();
    if (!materials.length) {
      const empty = document.createElement('p'); empty.className = 'empty-state';
      empty.textContent = 'Материалов пока нет. Администратор может добавить PDF, DOCX или TXT.';
      $('#material-list').append(empty);
    }
    materials.forEach(file => {
      const row = document.createElement('div'); row.className = 'material-row';
      const type = document.createElement('span'); type.className = 'doc-type'; type.textContent = file.name.split('.').pop().toUpperCase();
      const info = document.createElement('div'); info.className = 'file-info';
      const name = document.createElement('strong'); name.textContent = file.name;
      const meta = document.createElement('small'); meta.textContent = `${Math.max(1, Math.round(file.size / 1024))} КБ · ${file.characters.toLocaleString('ru-RU')} символов`;
      const actions = document.createElement('div'); actions.className = 'material-actions';
      const view = document.createElement('a'); view.textContent = 'Открыть ↗';
      view.href = `/api/materials/${encodeURIComponent(file.id)}/view`;
      view.target = '_blank'; view.rel = 'noopener';
      view.setAttribute('aria-label', 'Открыть ' + file.name);
      const download = document.createElement('a'); download.textContent = 'Скачать ↓';
      download.href = `/api/materials/${encodeURIComponent(file.id)}/download`;
      download.setAttribute('aria-label', 'Скачать ' + file.name);
      actions.append(view, download);
      info.append(name, meta, actions); row.append(type, info); $('#material-list').append(row);
    });
  } catch { $('#material-list').textContent = 'Не удалось загрузить список материалов. Проверьте сервер и попробуйте снова.'; }
}
async function showMaterials() { $('#materials-dialog').showModal(); await loadMaterials(); }
window.addEventListener('focus', () => { loadMaterials(); syncAccount(); });
$('#materials-button').addEventListener('click', showMaterials);
$('#composer-materials').addEventListener('click', showMaterials);
$('#close-dialog').addEventListener('click', () => $('#materials-dialog').close());
$('#new-chat').addEventListener('click', () => {
  if (busy) return;
  current = null; $('#prompt').value = ''; renderMessages(); closeMenu(); $('#prompt').focus();
});
$('#clear-history').addEventListener('click', () => {
  if (busy || !chats.length) return;
  if (confirm('Удалить все диалоги из этого браузера?')) {
    chats = []; current = null; save(); renderHistory(); renderMessages();
  }
});
document.querySelectorAll('[data-mode]').forEach(el => el.addEventListener('click', () => setMode(el.dataset.mode)));
$('#mode-select').addEventListener('change', e => setMode(e.target.value));
$('#menu').addEventListener('click', () => { const open = $('#sidebar').classList.toggle('open'); $('#menu').setAttribute('aria-expanded', String(open)); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
$('#prompt').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!busy) $('#chat-form').requestSubmit(); }
});
$('#chat-form').addEventListener('submit', async e => {
  e.preventDefault();
  const message = $('#prompt').value.trim();
  if (!message || busy) return;
  const submittedAccount = currentUser?.id || null;
  busy = true;
  await refreshStatus();
  if (!ready || submittedAccount !== (currentUser?.id || null)) { busy = false; return; }
  busy = true; $('#send').disabled = true; $('#mode-select').disabled = true;
  if (!current) {
    current = {id: crypto.randomUUID(), title: message.slice(0, 60), mode, messages: []};
    chats.unshift(current); chats = chats.slice(0, 30);
  }
  const history = current.messages.slice(-12).map(m => ({role: m.role, content: m.text}));
  const requestEpoch = accountEpoch;
  current.mode = mode;
  current.messages.push({role: 'user', text: message});
  $('#prompt').value = ''; renderMessages(); renderHistory(); save();
  const pending = document.createElement('div'); pending.className = 'pending'; pending.textContent = 'Подготовка ответа… Первый запуск локальной модели может занять до 3 минут.';
  $('#messages').append(pending); scrollToEnd();
  try {
    if (!connected) await refreshStatus();
    const result = await api('/api/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message, mode, history})});
    if (requestEpoch !== accountEpoch) return;
    const response = {role: 'assistant', text: result.text, demo: result.demo, sources: result.sources};
    current.messages.push(response);
    // Keep browser storage bounded. The full current message remains visible until this limit is reached.
    current.messages = current.messages.slice(-80);
    save(); appendMessage(response);
  } catch (error) {
    if (requestEpoch !== accountEpoch) return;
    const article = document.createElement('div'); article.className = 'message error'; article.setAttribute('role', 'alert');
    article.textContent = error.name === 'TimeoutError' ? 'Время ожидания истекло. Попробуйте ещё раз.' : error.message;
    $('#messages').append(article); $('#prompt').value = message;
    // Failed attempts must not become unanswered duplicate turns in the API history.
    current.messages.pop(); save();
  } finally {
    pending.remove(); busy = false; $('#send').disabled = false; $('#mode-select').disabled = false;
    scrollToEnd(); $('#prompt').focus();
  }
});
setMode(mode); renderHistory(); syncAccount().finally(refreshStatus); loadMaterials();
