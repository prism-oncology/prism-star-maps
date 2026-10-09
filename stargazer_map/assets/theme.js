(function(){
  // Light/dark toggle in the header. Follows the OS until the visitor picks a
  // theme; the pick is saved and applied before first paint by the inline script
  // in <head>. Fires a `themechange` event on window so map.js can repaint.
  var KEY = 'stargazer-map:theme';
  var root = document.documentElement;
  var media = window.matchMedia('(prefers-color-scheme: dark)');
  var button = document.getElementById('theme-toggle');
  var SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

  function current(){ return root.dataset.theme || (media.matches ? 'dark' : 'light'); }
  function render(){
    var dark = current() === 'dark';
    // Like mkdocs-material: the icon shows the theme you switch to.
    button.innerHTML = dark ? SUN : MOON;
    var label = dark ? 'Switch to light mode' : 'Switch to dark mode';
    button.setAttribute('aria-label', label);
    button.title = label;
  }
  function changed(){ render(); window.dispatchEvent(new Event('themechange')); }

  button.addEventListener('click', function(){
    root.dataset.theme = current() === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(KEY, root.dataset.theme); } catch(e) {}
    changed();
  });
  media.addEventListener('change', function(){ if (!root.dataset.theme) changed(); });
  render();
})();
