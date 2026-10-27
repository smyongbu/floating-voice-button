(() => {
  'use strict';
  const storageKey = 'voice-app-theme';
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  const validTheme = value => value === 'light' || value === 'dark';
  let savedTheme = null;
  try { savedTheme = localStorage.getItem(storageKey); } catch (_) { /* 本地存储受限时仍可切换。 */ }
  let manual = validTheme(savedTheme);
  let theme = manual ? savedTheme : (systemTheme.matches ? 'dark' : 'light');
  let buttons = [];
  const apply = value => {
    theme = value;
    document.documentElement.dataset.theme = theme;
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme)));
  };
  apply(theme);
  systemTheme.addEventListener('change', event => {
    if (!manual) apply(event.matches ? 'dark' : 'light');
  });
  document.addEventListener('DOMContentLoaded', () => {
    buttons = [...document.querySelectorAll('[data-theme-choice]')];
    apply(theme);
    buttons.forEach(button => button.addEventListener('click', () => {
      const value = button.dataset.themeChoice;
      if (!validTheme(value)) return;
      manual = true;
      apply(value);
      try { localStorage.setItem(storageKey, value); } catch (_) { /* 仅保留本次页面选择。 */ }
    }));
  });
})();
