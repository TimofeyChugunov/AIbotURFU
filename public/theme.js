'use strict';
(() => {
  const storageKey = 'aiboturfu.theme.v1';
  const root = document.documentElement;
  let selected = 'light';
  try { selected = localStorage.getItem(storageKey) === 'dark' ? 'dark' : 'light'; }
  catch { /* Theme switching also works when browser storage is disabled. */ }

  function apply(theme) {
    selected = theme === 'dark' ? 'dark' : 'light';
    root.dataset.theme = selected;
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const dark = selected === 'dark';
      const label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
      button.textContent = dark ? '☀' : '☾';
      button.title = label;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', String(dark));
    });
  }

  // This script runs in the head, before styles and the first page paint.
  apply(selected);
  document.addEventListener('DOMContentLoaded', () => {
    apply(selected);
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        apply(selected === 'dark' ? 'light' : 'dark');
        try { localStorage.setItem(storageKey, selected); } catch { /* Session-only choice. */ }
      });
    });
  });
  window.addEventListener('storage', event => {
    if (event.key === storageKey || event.key === null) apply(event.newValue);
  });
})();
