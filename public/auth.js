'use strict';
const find = selector => document.querySelector(selector);
let authMode = 'login';
let authBusy = false;
function notifyTabs() { try { localStorage.setItem('aiboturfu.auth.changed', crypto.randomUUID()); } catch { /* Cookies still work. */ } }
function feedback(message) { find('#auth-feedback').textContent = message; }
async function authRequest(path, data) {
  const response = await fetch(path, {method: data ? 'POST' : 'GET', headers: {'Content-Type': 'application/json'}, body: data ? JSON.stringify(data) : undefined, signal: AbortSignal.timeout(15000)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Не удалось выполнить запрос.');
  return result;
}
function setMode(mode) {
  if (authBusy) return;
  authMode = mode;
  const register = mode === 'register';
  document.querySelectorAll('[data-auth-mode]').forEach(button => {
    const active = button.dataset.authMode === mode;
    button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1;
  });
  find('#auth-form').setAttribute('aria-labelledby', register ? 'register-tab' : 'login-tab');
  find('#confirmation-field').hidden = !register;
  find('#password-confirm').required = register;
  find('#password-confirm').value = '';
  find('#account-password').value = '';
  find('#account-password').autocomplete = register ? 'new-password' : 'current-password';
  find('#auth-heading').textContent = register ? 'Давай познакомимся' : 'С возвращением';
  find('#auth-intro').textContent = register ? 'Создай аккаунт, чтобы возвращаться в своё пространство.' : 'Войди с Username и паролем, чтобы продолжить.';
  find('#auth-submit').textContent = register ? 'Создать аккаунт →' : 'Войти →';
  feedback('');
}
document.querySelectorAll('[data-auth-mode]').forEach(button => {
  button.addEventListener('click', () => setMode(button.dataset.authMode));
  button.addEventListener('keydown', event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      setMode(event.key === 'Home' ? 'login' : event.key === 'End' ? 'register' : authMode === 'login' ? 'register' : 'login');
      document.querySelector(`[data-auth-mode="${authMode}"]`).focus();
    }
  });
});
find('#auth-form').addEventListener('submit', async event => {
  event.preventDefault(); if (authBusy) return;
  const password = find('#account-password').value;
  if (authMode === 'register' && password !== find('#password-confirm').value) { feedback('Пароли не совпадают.'); find('#password-confirm').focus(); return; }
  authBusy = true; find('#auth-submit').disabled = true; feedback('');
  try {
    await authRequest('/api/auth/' + authMode, {username: find('#username').value.trim(), password});
    find('#auth-form').reset(); notifyTabs(); location.assign('/');
  } catch (error) {
    feedback(error.name === 'TimeoutError' ? 'Сервер не ответил. Попробуй ещё раз.' : error.message);
    authBusy = false; find('#auth-submit').disabled = false;
  }
});
find('#account-signout').addEventListener('click', async () => {
  if (authBusy) return;
  authBusy = true;
  try { await authRequest('/api/auth/logout', {}); notifyTabs(); location.reload(); }
  catch (error) { feedback(error.message); authBusy = false; }
});
(async () => {
  try {
    const result = await authRequest('/api/auth/me');
    find('#auth-forms').hidden = !!result.user;
    find('#account-session').hidden = !result.user;
    if (result.user) { find('#signed-in-user').textContent = result.user.username; find('#auth-intro').textContent = 'Аккаунт готов к работе.'; }
  } catch (error) { feedback('Не удалось подключиться к серверу. Обнови страницу и попробуй ещё раз.'); }
})();
