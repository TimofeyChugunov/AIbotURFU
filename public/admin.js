'use strict';
const $ = selector => document.querySelector(selector);
let admin = false;
let uploading = false;
let selected = [];
let adminEpoch = 0;
let passwordUser = null;
function feedback(message, error = false) { $('#feedback').textContent = message; $('#feedback').classList.toggle('error', error); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(75000)});
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) setAdmin(false); throw new Error(data.error || 'Ошибка запроса.'); }
  return data;
}
function post(path, data) { return api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)}); }
function setAdmin(value) {
  admin = value;
  adminEpoch++;
  $('#login-panel').hidden = value;
  $('#manage-panel').hidden = !value;
  $('#users-panel').hidden = !value;
  if (!value) {
    $('#admin-users').replaceChildren();
    $('#users-total').textContent = '0';
    $('#users-feedback').textContent = '';
    $('#reset-password-dialog').close();
    $('#reset-password-form').reset();
    passwordUser = null;
  }
}

function usersFeedback(message, error = false) {
  $('#users-feedback').textContent = message;
  $('#users-feedback').classList.toggle('error', error);
}

async function renderUsers() {
  if (!admin) return;
  const epoch = adminEpoch;
  const users = await api('/api/admin/users');
  if (!admin || epoch !== adminEpoch) return;
  $('#users-total').textContent = users.length;
  $('#admin-users').replaceChildren();
  if (!users.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Зарегистрированных пользователей пока нет.';
    $('#admin-users').append(empty);
  }
  users.forEach(user => {
    const row = document.createElement('div');
    row.className = 'material-row user-row';
    const info = document.createElement('div');
    info.className = 'file-info';
    const name = document.createElement('strong');
    name.textContent = user.username;
    const date = document.createElement('small');
    date.textContent = 'Регистрация: ' + new Date(user.created * 1000).toLocaleString('ru-RU');
    info.append(name, date);
    const actions = document.createElement('div');
    actions.className = 'user-actions';
    const reset = document.createElement('button');
    reset.type = 'button';
    reset.className = 'reset-user-password';
    reset.textContent = 'Сбросить пароль';
    reset.setAttribute('aria-label', 'Сбросить пароль ' + user.username);
    reset.addEventListener('click', () => {
      passwordUser = user;
      $('#reset-password-form').reset();
      $('#password-feedback').textContent = '';
      $('#reset-password-user').textContent = 'Пользователь: ' + user.username;
      $('#reset-password-dialog').showModal();
      $('#new-user-password').focus();
    });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'delete-user';
    remove.textContent = 'Удалить';
    remove.setAttribute('aria-label', 'Удалить пользователя ' + user.username);
    remove.addEventListener('click', async () => {
      if (!confirm(`Удалить аккаунт «${user.username}»? Все его сеансы будут завершены. История чатов в браузере не удаляется.`)) return;
      reset.disabled = true;
      remove.disabled = true;
      try {
        await api('/api/admin/users/' + user.id, {method: 'DELETE'});
        if (admin && epoch === adminEpoch) {
          await renderUsers();
          usersFeedback('Аккаунт удалён.');
        }
      } catch (error) { if (admin) usersFeedback(error.message, true); }
      finally { reset.disabled = false; remove.disabled = false; }
    });
    actions.append(reset, remove);
    row.append(info, actions);
    $('#admin-users').append(row);
  });
}

$('#refresh-users').addEventListener('click', async () => {
  try { await renderUsers(); usersFeedback('Список обновлён.'); }
  catch (error) { if (admin) usersFeedback(error.message, true); }
});
$('#cancel-password').addEventListener('click', () => $('#reset-password-dialog').close());
$('#reset-password-dialog').addEventListener('close', () => {
  $('#reset-password-form').reset();
  passwordUser = null;
});
$('#reset-password-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!admin || !passwordUser) return;
  const password = $('#new-user-password').value;
  if (password !== $('#confirm-user-password').value) {
    $('#password-feedback').textContent = 'Пароли не совпадают.';
    return;
  }
  const epoch = adminEpoch;
  const user = passwordUser;
  $('#save-user-password').disabled = true;
  try {
    await post('/api/admin/users/' + user.id + '/password', {password});
    if (admin && epoch === adminEpoch) {
      $('#reset-password-dialog').close();
      $('#reset-password-form').reset();
      usersFeedback(`Пароль пользователя «${user.username}» изменён. Все его сеансы завершены.`);
    }
  } catch (error) {
    if (admin && epoch === adminEpoch) $('#password-feedback').textContent = error.message;
  } finally { $('#save-user-password').disabled = false; }
});
async function renderMaterials() {
  const files = await api('/api/materials');
  $('#total').textContent = files.length;
  $('#admin-materials').replaceChildren();
  if (!files.length) {
    const empty = document.createElement('p'); empty.className = 'empty-state';
    empty.textContent = 'Здесь пока пусто. Добавьте первые учебные материалы.';
    $('#admin-materials').append(empty);
  }
  files.forEach(file => {
    const row = document.createElement('div'); row.className = 'material-row';
    const icon = document.createElement('span'); icon.className = 'doc-type'; icon.textContent = file.name.split('.').pop().toUpperCase();
    const info = document.createElement('div'); info.className = 'file-info';
    const name = document.createElement('strong'); name.textContent = file.name;
    const meta = document.createElement('small'); meta.textContent = `${Math.max(1, Math.round(file.size / 1024))} КБ · ${file.characters.toLocaleString('ru-RU')} символов · Текст извлечён`;
    const actions = document.createElement('div'); actions.className = 'material-actions';
    const view = document.createElement('a'); view.textContent = 'Открыть ↗';
    view.href = `/api/materials/${encodeURIComponent(file.id)}/view`; view.target = '_blank'; view.rel = 'noopener';
    const download = document.createElement('a'); download.textContent = 'Скачать ↓';
    download.href = `/api/materials/${encodeURIComponent(file.id)}/download`;
    actions.append(view, download);
    info.append(name, meta, actions); row.append(icon, info);
    if (admin) {
      const button = document.createElement('button'); button.textContent = 'Удалить'; button.setAttribute('aria-label', 'Удалить ' + file.name);
      button.addEventListener('click', async () => {
        if (!confirm(`Удалить «${file.name}» из базы знаний?`)) return;
        button.disabled = true;
        try { await api('/api/materials/' + file.id, {method: 'DELETE'}); await renderMaterials(); feedback('Материал удалён.'); }
        catch (error) { feedback(error.message, true); button.disabled = false; }
      });
      row.append(button);
    }
    $('#admin-materials').append(row);
  });
}
$('#login-form').addEventListener('submit', async e => {
  e.preventDefault(); const button = e.submitter; button.disabled = true;
  try { await post('/api/login', {password: $('#password').value}); $('#password').value = ''; setAdmin(true); await Promise.all([renderMaterials(), renderUsers()]); feedback('Вход выполнен. Можно управлять материалами и пользователями.'); }
  catch (error) { feedback(error.message, true); }
  finally { button.disabled = false; }
});
$('#logout').addEventListener('click', async () => {
  if (uploading) return;
  try { await post('/api/logout', {}); setAdmin(false); await renderMaterials(); feedback('Вы вышли из панели администратора.'); }
  catch (error) { feedback(error.message, true); }
});
function selectFiles(files) {
  selected = Array.from(files);
  $('#selected-files').textContent = selected.map(f => f.name).join(', ');
  $('#upload-button').disabled = !selected.length || uploading;
}
$('#files').addEventListener('change', e => selectFiles(e.target.files));
const zone = $('#upload-form');
['dragenter', 'dragover'].forEach(event => zone.addEventListener(event, e => { e.preventDefault(); zone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach(event => zone.addEventListener(event, e => { e.preventDefault(); zone.classList.remove('dragging'); }));
zone.addEventListener('drop', e => { if (!uploading) selectFiles(e.dataTransfer.files); });
function encodeFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(new Error('Не удалось прочитать файл.'));
    reader.readAsDataURL(file);
  });
}
zone.addEventListener('submit', async e => {
  e.preventDefault(); if (uploading || !selected.length) return;
  uploading = true; $('#upload-button').disabled = true; $('#files').disabled = true; $('#logout').disabled = true;
  const results = []; const failed = []; const batch = [...selected];
  for (let index = 0; index < batch.length; index++) {
    const file = batch[index];
    feedback(`Загрузка ${index + 1} из ${batch.length}: ${file.name}`);
    try {
      if (!/\.(pdf|docx|txt)$/i.test(file.name)) throw new Error('Поддерживаются только PDF, DOCX и TXT.');
      if (!file.size || file.size > 10 * 1024 * 1024) throw new Error('Допустимый размер — от 1 байта до 10 МБ.');
      const content = await encodeFile(file);
      const result = await post('/api/materials', {name: file.name, content});
      results.push(`${file.name}: загружен, ${result.characters.toLocaleString('ru-RU')} символов.`);
    } catch (error) { failed.push(file); results.push(`${file.name}: ${error.message}`); }
  }
  uploading = false; $('#files').disabled = false; $('#logout').disabled = false;
  selectFiles(failed); $('#files').value = '';
  feedback(results.join('\n'), !!failed.length);
  try { await renderMaterials(); } catch (error) { feedback(results.join('\n') + '\n' + error.message, true); }
});
(async () => {
  try { const status = await api('/api/status'); setAdmin(status.admin); await Promise.all([renderMaterials(), renderUsers()]); }
  catch (error) { feedback('Не удалось подключиться к серверу: ' + error.message, true); }
})();
