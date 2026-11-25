/* ViewDeals on-page search. No requests, no storage, no tracking. */
(function () {
  var input = document.getElementById('q');
  if (!input) return;
  var cards = [].slice.call(document.querySelectorAll('[data-search]'));
  var sections = [].slice.call(document.querySelectorAll('[data-search-section]'));
  var empty = document.getElementById('search-empty');

  function run() {
    var words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    var shown = 0;
    cards.forEach(function (card) {
      var text = card.getAttribute('data-search');
      var match = words.every(function (w) { return text.indexOf(w) !== -1; });
      card.hidden = !match;
      if (match) shown++;
    });
    sections.forEach(function (s) {
      s.hidden = !s.querySelector('[data-search]:not([hidden])');
    });
    if (empty) empty.hidden = shown > 0;
  }

  var q = new URLSearchParams(window.location.search).get('q');
  if (q) { input.value = q; run(); }
  input.addEventListener('input', run);
  input.form && input.form.addEventListener('submit', function (ev) { ev.preventDefault(); run(); });
})();
