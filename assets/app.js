/*
 * InfraGov — client-side helpers. Loaded from /assets (same origin), so the
 * Content-Security-Policy can forbid inline scripts entirely. No data is
 * rendered as HTML here; only classes / attributes are toggled.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------- clientside callbacks
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    infragov: {
      charCount: function (v) { return (v || '').length + '/100'; },
      charCount200: function (v) { return (v || '').length + '/200'; },
      charCount2000: function (v) { return (v || '').length + '/2000'; },
      markDirty: function () { return true; },
      clearSaveStatus: function (dirty) { return dirty ? '' : window.dash_clientside.no_update; },
      panelMargin: function (state) {
        var base = 'flex-1 min-w-0 px-8 py-6 transition-all';
        return state && state.open ? base + ' mr-96' : base;
      }
    }
  });

  function navigate(href) {
    window.history.pushState({}, '', href);
    window.dispatchEvent(new CustomEvent('_dashprivate_pushstate'));
    window.scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- delegated events
  document.addEventListener('click', function (e) {
    var t = e.target;

    // Close any open dropdown menu when clicking outside it, or after choosing an item.
    document.querySelectorAll('details.ig-menu[open]').forEach(function (d) {
      var inSummary = t.closest('summary') && d.contains(t.closest('summary'));
      if (inSummary) return;
      var item = t.closest('a, button');
      var chose = item && d.contains(item);
      var typing = t.closest('textarea, input');
      if (!d.contains(t) || (chose && !typing)) d.removeAttribute('open');
    });

    // Whole-row navigation on tables (keeps an inner <a> for keyboard / new-tab use).
    var row = t.closest('tr.ig-clickable-row');
    if (row && !t.closest('a,button')) {
      var href = row.getAttribute('data-href');
      if (href && href.charAt(0) === '/' ) navigate(href);
    }

    // Print buttons.
    if (t.closest('#report-print') || t.closest('#cp-pdf')) window.print();

    // Show / hide password.
    var tog = t.closest('#login-toggle-pw, #reset-toggle-pw');
    if (tog) {
      var input = tog.parentElement.querySelector('input');
      if (input) input.type = input.type === 'password' ? 'text' : 'password';
    }
  });

  // FAQ accordion: keep a single item open.
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (d.classList && d.classList.contains('ig-accordion') && d.open) {
      d.parentElement.querySelectorAll('details.ig-accordion[open]').forEach(function (o) { if (o !== d) o.removeAttribute('open'); });
    }
  }, true);

  // Landing page feature tabs (hover / focus swaps the screenshot).
  function activateFeature(el) {
    var wrap = el.closest('.ig-features');
    if (!wrap) return;
    var idx = el.getAttribute('data-feature');
    wrap.querySelectorAll('.ig-feature').forEach(function (f) {
      var on = f.getAttribute('data-feature') === idx;
      f.classList.toggle('border-l-indigo-400', on);
      f.classList.toggle('bg-white/[0.06]', on);
      f.classList.toggle('border-l-transparent', !on);
      var n = f.querySelector('.ig-feature-num'); var tx = f.querySelector('.ig-feature-text');
      if (n) { n.classList.toggle('text-indigo-400', on); n.classList.toggle('text-gray-600', !on); }
      if (tx) { tx.classList.toggle('text-white', on); tx.classList.toggle('text-gray-400', !on); }
    });
    wrap.querySelectorAll('.ig-feature-img').forEach(function (img) {
      var on = img.getAttribute('data-feature-img') === idx;
      img.classList.toggle('opacity-100', on);
      img.classList.toggle('opacity-0', !on);
    });
  }
  document.addEventListener('mouseover', function (e) {
    var f = e.target.closest && e.target.closest('.ig-feature');
    if (f) activateFeature(f);
  });
  document.addEventListener('focusin', function (e) {
    var f = e.target.closest && e.target.closest('.ig-feature');
    if (f) activateFeature(f);
  });

  // About page: smooth scroll + scroll-spy.
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a.ig-spy');
    if (!a) return;
    var id = a.getAttribute('data-spy');
    var el = document.getElementById(id);
    if (el) { e.preventDefault(); el.scrollIntoView({ behavior: 'smooth', block: 'start' }); setSpy(id); }
  });
  function setSpy(id) {
    document.querySelectorAll('a.ig-spy').forEach(function (a) {
      var on = a.getAttribute('data-spy') === id;
      a.classList.toggle('text-indigo-300', on); a.classList.toggle('font-semibold', on); a.classList.toggle('text-gray-300', !on);
      var i = a.querySelector('.ig-spy-icon');
      if (i) { i.classList.toggle('text-indigo-300', on); i.classList.toggle('text-gray-500', !on); }
    });
  }
  var spyObserver = null;
  function wireSpy() {
    if (spyObserver) { spyObserver.disconnect(); spyObserver = null; }
    var sections = document.querySelectorAll('.ig-about main section[id]');
    if (!sections.length || !('IntersectionObserver' in window)) return;
    spyObserver = new IntersectionObserver(function (entries) {
      var vis = entries.filter(function (x) { return x.isIntersecting; });
      if (!vis.length) return;
      vis.sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });
      setSpy(vis[0].target.id);
    }, { rootMargin: '-80px 0px -65% 0px', threshold: 0 });
    sections.forEach(function (s) { spyObserver.observe(s); });
    var p = new URLSearchParams(window.location.search).get('section');
    if (p && document.getElementById(p)) document.getElementById(p).scrollIntoView({ block: 'start' });
  }

  // Re-wire page behaviours whenever Dash swaps the page content.
  var printed = {};
  new MutationObserver(function () {
    if (document.querySelector('.ig-about') && !document.querySelector('.ig-about[data-wired]')) {
      document.querySelector('.ig-about').setAttribute('data-wired', '1');
      wireSpy();
    }
    var rep = document.querySelector('.ig-autoprint');
    if (rep && !printed[window.location.search]) {
      printed[window.location.search] = true;
      setTimeout(function () { window.print(); }, 400);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
