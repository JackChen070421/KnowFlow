// Runs synchronously in <head>: restore the saved palette before first paint,
// so switching pages never flashes the default light theme.
(function () {
  var THEMES = ['light', 'dark', 'eye'];
  var stored = null;
  try {
    stored = localStorage.getItem('knowflow.theme');
  } catch (error) {
    stored = null;
  }
  var fromUrl = new URLSearchParams(location.search).get('theme');
  var theme = THEMES.indexOf(fromUrl) >= 0 ? fromUrl : stored;
  if (THEMES.indexOf(theme) < 0) theme = 'light';
  document.documentElement.setAttribute('data-theme', theme);
})();
