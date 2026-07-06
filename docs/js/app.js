/* Trans Violence Tracker — article list + filters.
 *
 * Security notes:
 *  - All article data is treated as UNTRUSTED (titles/summaries originate from
 *    scraped web pages). Rendering uses document.createElement + textContent
 *    exclusively — no innerHTML, no inline styles, no eval.
 *  - Article links are only rendered as clickable if the URL parses and its
 *    protocol is http: or https: (blocks javascript:, data:, etc.).
 *  - External links open with rel="noopener noreferrer"; the page-level
 *    referrer policy is no-referrer.
 */
'use strict';

(function () {
  var DATA_URL = 'data/articles.json';

  var VIOLENCE_LABELS = {
    murder: 'Murder',
    sexual_assault: 'Sexual assault',
    physical_assault: 'Physical assault',
    police_brutality: 'Police brutality',
    mob_violence: 'Mob violence',
    institutional: 'Institutional'
  };

  var els = {
    cards: document.getElementById('cards'),
    count: document.getElementById('result-count'),
    from: document.getElementById('filter-from'),
    to: document.getElementById('filter-to'),
    state: document.getElementById('filter-state'),
    lang: document.getElementById('filter-lang'),
    clear: document.getElementById('filter-clear')
  };

  var articles = [];

  /* ── Helpers ─────────────────────────────────────────────── */

  function asText(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  /* Prefer incident_date (YYYY-MM-DD); fall back to published_date,
     which the pipeline stores as YYYYMMDD. Returns '' if neither parses. */
  function isoDate(article) {
    var inc = asText(article.incident_date);
    if (/^\d{4}-\d{2}-\d{2}$/.test(inc)) return inc;
    var pub = asText(article.published_date);
    if (/^\d{8}$/.test(pub)) {
      return pub.slice(0, 4) + '-' + pub.slice(4, 6) + '-' + pub.slice(6, 8);
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(pub)) return pub;
    return '';
  }

  function displayDate(iso) {
    if (!iso) return 'Date unknown';
    var d = new Date(iso + 'T00:00:00');
    if (isNaN(d.getTime())) return 'Date unknown';
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  /* Only http(s) URLs are allowed to become links. */
  function safeUrl(value) {
    try {
      var url = new URL(String(value));
      if (url.protocol === 'https:' || url.protocol === 'http:') return url.href;
    } catch (e) { /* unparseable — treat as no link */ }
    return null;
  }

  function stateName(article) {
    return asText(article.state) || 'Unknown';
  }

  /* Data has no language column yet; everything collected so far is English. */
  function langCode(article) {
    return asText(article.language).toLowerCase() || 'en';
  }

  /* ── Rendering (DOM API only — never innerHTML) ──────────── */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function buildCard(article) {
    var url = safeUrl(article.url);
    var card = el(url ? 'a' : 'article', 'card');
    if (url) {
      card.href = url;
      card.target = '_blank';
      card.rel = 'noopener noreferrer';
    }

    var meta = el('div', 'card-meta');
    var type = asText(article.violence_type);
    meta.appendChild(el('span',
      'badge' + (type === 'murder' ? ' fatal' : ''),
      VIOLENCE_LABELS[type] || 'Other'));

    var outcome = asText(article.outcome);
    if (outcome === 'victim_died') {
      meta.appendChild(el('span', 'badge fatal', 'Victim died'));
    } else if (outcome === 'victim_survived') {
      meta.appendChild(el('span', 'badge outcome', 'Victim survived'));
    }

    var victims = Number(article.victim_count);
    if (Number.isFinite(victims) && victims > 1) {
      meta.appendChild(el('span', 'badge outcome', victims + ' victims'));
    }

    meta.appendChild(el('span', 'card-date', displayDate(isoDate(article))));
    card.appendChild(meta);

    card.appendChild(el('h2', null, asText(article.title) || 'Untitled article'));

    var summary = asText(article.summary);
    if (summary) card.appendChild(el('p', 'summary', summary));

    var foot = el('div', 'card-foot');
    var place = [asText(article.city), stateName(article)].filter(Boolean).join(', ');
    foot.appendChild(el('span', null, '\u{1F4CD} ' + place));
    var source = asText(article.source_name) || asText(article.source_domain);
    if (source) foot.appendChild(el('span', null, '\u{1F4F0} ' + source));
    if (url) foot.appendChild(el('span', null, 'Read the full article →'));
    card.appendChild(foot);

    return card;
  }

  /* ── Filtering ───────────────────────────────────────────── */

  function applyFilters() {
    var from = asText(els.from.value);
    var to = asText(els.to.value);
    var stateFilter = els.state.value;
    var langFilter = els.lang.value;

    var shown = articles.filter(function (a) {
      var iso = isoDate(a);
      if (from && (!iso || iso < from)) return false;
      if (to && (!iso || iso > to)) return false;
      if (stateFilter !== 'all' && stateName(a) !== stateFilter) return false;
      if (langFilter !== 'all' && langCode(a) !== langFilter) return false;
      return true;
    });

    els.cards.replaceChildren();
    if (shown.length === 0) {
      els.cards.appendChild(el('p', 'notice', 'No articles match the current filters.'));
    } else {
      shown.forEach(function (a) { els.cards.appendChild(buildCard(a)); });
    }
    els.count.textContent = 'Showing ' + shown.length + ' of ' + articles.length + ' articles';
  }

  function populateStates() {
    var names = {};
    articles.forEach(function (a) { names[stateName(a)] = true; });
    Object.keys(names).sort().forEach(function (name) {
      var opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      els.state.appendChild(opt);
    });
  }

  function clearFilters() {
    els.from.value = '';
    els.to.value = '';
    els.state.value = 'all';
    els.lang.value = 'all';
    applyFilters();
  }

  /* ── Init ────────────────────────────────────────────────── */

  [els.from, els.to, els.state, els.lang].forEach(function (input) {
    input.addEventListener('change', applyFilters);
  });
  els.clear.addEventListener('click', clearFilters);

  fetch(DATA_URL, { credentials: 'omit' })
    .then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function (data) {
      if (!Array.isArray(data)) throw new Error('Unexpected data format');
      articles = data.filter(function (a) { return a && typeof a === 'object'; });
      /* Newest first by the same date used for display/filtering. */
      articles.sort(function (a, b) {
        return isoDate(b).localeCompare(isoDate(a));
      });
      populateStates();
      applyFilters();
    })
    .catch(function (err) {
      els.cards.replaceChildren(
        el('p', 'notice', 'Could not load the article data (' + err.message + '). Please try again later.')
      );
    });
})();
