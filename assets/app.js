/* ViewDeals: on-page search, the edition (theme) toggle, and scroll-in motion.
   No requests, no tracking. The only storage is the reader's chosen edition. */
(function () {
  var root = document.documentElement;

  /* Search (home page only). */
  var input = document.getElementById('q');
  if (input) {
    var cards = [].slice.call(document.querySelectorAll('[data-search]'));
    var sections = [].slice.call(document.querySelectorAll('[data-search-section]'));
    var empty = document.getElementById('search-empty');
    var run = function () {
      var words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      var shown = 0;
      cards.forEach(function (card) {
        var text = card.getAttribute('data-search');
        var match = words.every(function (w) { return text.indexOf(w) !== -1; });
        card.hidden = !match;
        if (match) shown++;
      });
      sections.forEach(function (s) { s.hidden = !s.querySelector('[data-search]:not([hidden])'); });
      if (empty) empty.hidden = shown > 0;
    };
    var q = new URLSearchParams(window.location.search).get('q');
    if (q) { input.value = q; run(); }
    input.addEventListener('input', run);
    if (input.form) input.form.addEventListener('submit', function (ev) { ev.preventDefault(); run(); });
  }

  /* Day / night edition toggle. */
  var toggle = document.querySelector('[data-theme-toggle]');
  var isDark = function () {
    var set = root.getAttribute('data-theme');
    return set ? set === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  };
  var label = function () { if (toggle) toggle.textContent = isDark() ? 'Switch to day edition' : 'Switch to night edition'; };
  if (toggle) {
    label();
    toggle.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('vd-theme', next); } catch (e) {}
      label();
    });
  }

  /* Stamps press in and annotation marks draw themselves, once, when they scroll into view. */
  var moving = [].slice.call(document.querySelectorAll('.stamp, .mark'));
  var reveal = function (el) { el.classList.add('is-in'); };
  if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    moving.forEach(reveal);
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { reveal(en.target); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -10% 0px' });
    moving.forEach(function (el) { io.observe(el); });
  }
})();
