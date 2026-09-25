/* Shared page chrome for Last-Mile Assist / Alert.
 *
 * Three jobs, none of which belong in the page logic:
 *
 *   1. Low-data mode. A household on a degraded cell tower after a storm is
 *      the actual user. Low-data drops the web fonts (~50 KB on an English page), the animation
 *      and the decorative weight, and tells the API not to synthesise audio.
 *      It removes no function: every control, every citation and every
 *      verification step stays exactly where it was.
 *
 *   2. Hiding navigation that points at nothing. The result sections start
 *      hidden, so a link to one before you have searched is a link to a blank
 *      screen. Those links stay out of the DOM until their section fills.
 *
 *   3. The figures band. Real counts from the API, not decoration - if the
 *      number cannot be fetched the whole band stays away.
 */

(function () {
  'use strict';

  const doc = document.documentElement;
  const LS_KEY = 'lm-lowdata';

  /* ------------------------------------------------------------ low data */

  // Set as early as possible by the inline snippet in <head>; this is the
  // fallback for when that snippet did not run.
  function lowDataOn() { return doc.hasAttribute('data-lowdata'); }

  function setLowData(on) {
    if (on) doc.setAttribute('data-lowdata', '');
    else doc.removeAttribute('data-lowdata');
    try { localStorage.setItem(LS_KEY, on ? '1' : '0'); } catch (e) { /* private mode */ }
    paintToggle();
    paintWeight();
  }

  function paintToggle() {
    const b = document.getElementById('lowdata-toggle');
    if (!b) return;
    const on = lowDataOn();
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    b.querySelector('.state').textContent = on ? 'On' : 'Off';
  }

  /* Bytes actually pulled over the wire, from the Resource Timing API. It is
     the honest number: transferSize counts headers and counts a cache hit as
     zero, which is what the household's data plan sees. */
  function pageWeight() {
    if (!window.performance || !performance.getEntriesByType) return null;
    const nav = performance.getEntriesByType('navigation')[0];
    let total = nav && nav.transferSize ? nav.transferSize : 0;
    performance.getEntriesByType('resource').forEach((r) => { total += r.transferSize || 0; });
    return total;
  }

  function paintWeight() {
    const el = document.getElementById('page-weight');
    if (!el) return;
    const bytes = pageWeight();
    if (bytes == null) { el.textContent = ''; return; }
    // A warm cache legitimately reads near zero: that is what the data plan sees.
    el.textContent = (bytes / 1024).toFixed(0) + ' KB over the wire this visit';
  }

  /* ------------------------------------------------- dead-link suppression */

  /* A link whose target section is hidden or empty goes away. Called again
     whenever the page logic reveals a section, so the links come back the
     moment there is something behind them. */
  function syncSectionLinks() {
    paintWeight();
    document.querySelectorAll('[data-needs]').forEach((el) => {
      const target = document.getElementById(el.dataset.needs);
      const live = !!target && !target.hidden && target.innerText.trim().length > 0;
      el.hidden = !live;
    });
  }

  // The page logic flips .hidden on sections directly, so watch for it rather
  // than asking every caller to remember to tell us.
  function watchSections() {
    const targets = [...document.querySelectorAll('[data-needs]')]
      .map((el) => document.getElementById(el.dataset.needs))
      .filter(Boolean);
    if (!targets.length) return;
    const obs = new MutationObserver(syncSectionLinks);
    targets.forEach((t) => obs.observe(t, {
      attributes: true, attributeFilter: ['hidden'], childList: true, subtree: true,
    }));
  }

  /* ------------------------------------------------------- figures band */

  const num = (n) => Number(n).toLocaleString('en-US');

  async function json(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(path + ' ' + r.status);
    return r.json();
  }

  function renderFigures(band, figures) {
    band.innerHTML = figures.map((f) => `
      <div class="figure">
        <div class="figure-n">${f.n}</div>
        <div class="figure-l">${f.label}</div>
        ${f.note ? `<div class="figure-note">${f.note}</div>` : ''}
      </div>`).join('');
    band.hidden = false;
  }

  async function figuresForNavigator(band) {
    const [impact, needs, health] = await Promise.all([
      json('api/assist/impact'), json('api/assist/needs'), json('api/health'),
    ]);
    renderFigures(band, [
      { n: num(impact.valid_registrations), label: 'Valid registrations',
        note: `DR-${impact.disaster_number}, FEMA IA` },
      { n: num(impact.counties), label: 'Counties in the declaration',
        note: `${num(impact.owner)} owner &middot; ${num(impact.renter)} renter` },
      { n: num(needs.needs.length), label: 'Situations we can route',
        note: 'Each one maps to cited programs' },
      { n: num(Object.keys(health.languages || {}).length + 1), label: 'Languages',
        note: 'Withheld when unverifiable' },
    ]);
  }

  async function figuresForAlert(band) {
    const stats = await json('api/corpus/stats');
    const events = Object.keys(stats.by_event || {}).length;
    renderFigures(band, [
      { n: num(stats.alerts), label: 'Real NWS alerts cached',
        note: 'Replayed offline, never re-issued' },
      { n: Math.round((stats.pct_with_instruction || 0) * 100) + '%',
        label: 'Carry an instruction field', note: `${num(stats.with_instruction)} of ${num(stats.alerts)}` },
      { n: Math.round((stats.pct_with_geometry || 0) * 100) + '%',
        label: 'Carry a polygon', note: 'Drawn from the alert own geometry' },
      { n: num(events), label: 'Event types', note: 'Warnings, advisories, statements' },
    ]);
  }

  async function loadFigures() {
    const band = document.getElementById('figures');
    if (!band) return;
    try {
      if (band.dataset.kind === 'alert') await figuresForAlert(band);
      else await figuresForNavigator(band);
    } catch (e) {
      band.remove();   // nothing behind it, so it does not get to sit there
    }
  }

  /* ------------------------------------------------------------- wire up */

  function init() {
    const toggle = document.getElementById('lowdata-toggle');
    if (toggle) toggle.addEventListener('click', () => setLowData(!lowDataOn()));
    paintToggle();

    const banner = document.getElementById('banner-toggle');
    if (banner) {
      banner.addEventListener('click', () => {
        const panel = document.getElementById('banner-panel');
        const open = banner.getAttribute('aria-expanded') === 'true';
        banner.setAttribute('aria-expanded', open ? 'false' : 'true');
        panel.hidden = open;
      });
    }

    // Delegated, because most accordions are written into the page by the
    // result renderers long after this runs.
    document.addEventListener('click', (e) => {
      const h = e.target.closest && e.target.closest('.accordion-head');
      if (!h) return;
      const open = h.getAttribute('aria-expanded') === 'true';
      h.setAttribute('aria-expanded', open ? 'false' : 'true');
      if (h.nextElementSibling) h.nextElementSibling.hidden = open;
    });

    syncSectionLinks();
    watchSections();
    loadFigures();
    window.addEventListener('load', paintWeight);
  }

  // Page logic asks us whether to spend the bytes on synthesised speech.
  window.lmLowData = lowDataOn;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
