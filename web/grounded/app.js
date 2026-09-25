/* Last-Mile Alert front end. Vanilla JS, no build step, no CDN.
 *
 * The map is hand-drawn SVG. That is a deliberate choice, not a shortcut: a
 * tile layer needs a network and a key, and brief section 12 says never demo
 * against infrastructure you do not control. Polygon, household pin, and the
 * line to the nearest edge are the three things a reader actually needs, and
 * all three come from the API response.
 */

const $ = (id) => document.getElementById(id);
const api = (path, opts) => fetch(path, opts).then(async (r) => {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `${r.status} ${r.statusText}`);
  return body;
});
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let STATE = { alertId: null, address: null, alerts: [], render: null, health: null };

/* ------------------------------------------------------------------ health */

async function loadHealth() {
  try {
    const h = await api('api/health');
    STATE.health = h;
    const live = h.providers.translator.startsWith('azure');
    const badge = $('engine-badge');
    badge.className = 'badge ' + (live ? 'live' : 'local');
    badge.textContent = live ? 'AZURE LIVE' : 'LOCAL FALLBACK ENGINES';
    badge.title = JSON.stringify(h.providers, null, 2);
    $('corpus-badge').textContent =
      `${h.corpus.cached_alerts} cached alerts · ${h.corpus.with_instruction} with instructions`;

    const sel = $('lang');
    sel.innerHTML = '<option value="en">English (plain)</option>' +
      Object.entries(h.languages).map(([code, meta]) =>
        `<option value="${esc(code)}">${esc(meta.name)}</option>`).join('');

    if (!live) {
      $('addr-hint').innerHTML += `<br><span style="color:#e6c77a">
        Local fallback engines are active: translation is glossary substitution, not
        machine translation, and simplification is rule-based. Output is labelled as
        such throughout. Set the Azure keys for production behaviour.</span>`;
    }
  } catch (e) {
    $('engine-badge').textContent = 'API unreachable';
  }
}

/* ------------------------------------------------------------------ locate */

async function findAlerts() {
  const address = $('addr').value.trim();
  if (!address) return;
  STATE.address = address;
  $('locate-out').innerHTML = '<div class="loading">Geocoding and testing against every cached polygon&hellip;</div>';
  $('alerts-sec').hidden = true;
  $('render-sec').hidden = true;
  $('prov-sec').hidden = true;

  let res;
  try {
    res = await api('api/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
    });
  } catch (e) {
    $('locate-out').innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }

  const g = res.geocode;
  $('locate-out').innerHTML = `
    <div class="kv" style="margin-top:10px">
      matched <b>${esc(g.matched_address)}</b><br>
      ${g.lat.toFixed(5)}, ${g.lon.toFixed(5)} &middot; via ${esc(g.source)}
      ${res.geocode_caveat ? `<br><span style="color:#e6c77a">${esc(res.geocode_caveat)}</span>` : ''}
    </div>`;

  STATE.alerts = [...res.inside, ...res.near_edge];
  const list = $('alert-list');
  if (!STATE.alerts.length) {
    list.innerHTML = `<div class="hint">No cached alert polygon contains or nearly contains this
      point. The corpus holds ${esc(res.counts.searched)} real alerts; try a Virginia address in
      the south-west, or an address near one of the cached national events.</div>`;
    $('alerts-sec').hidden = false;
    return;
  }

  list.innerHTML = STATE.alerts.map((a, i) => {
    const rel = a.relation;
    const pill = rel.status === 'inside'
      ? '<span class="pill inside">INSIDE</span>'
      : `<span class="pill near">${rel.distance_km} km OUTSIDE</span>`;
    return `<div class="alert-card" data-i="${i}">
      <div class="ev">${esc(a.event)}${pill}</div>
      <div class="meta">${esc(a.areaDesc)} &middot; ${esc(a.senderName)}</div>
      <div class="meta">sent ${esc(a.sent)}${a.has_instruction ? '' :
        ' &middot; <span style="color:var(--warn)">no instruction field</span>'}</div>
    </div>`;
  }).join('');

  list.querySelectorAll('.alert-card').forEach((el) => {
    el.onclick = () => {
      list.querySelectorAll('.alert-card').forEach((x) => x.classList.remove('sel'));
      el.classList.add('sel');
      STATE.alertId = STATE.alerts[+el.dataset.i].id;
      doRender();
    };
  });
  $('alerts-sec').hidden = false;

  // Pick the first alert that actually carries instructions - that is the one
  // with something to show.
  const first = list.querySelector('.alert-card');
  const idx = STATE.alerts.findIndex((a) => a.has_instruction);
  const target = idx >= 0 ? list.querySelectorAll('.alert-card')[idx] : first;
  if (target) target.click();
}

/* ------------------------------------------------------------------ render */

async function doRender() {
  if (!STATE.alertId) return;
  $('render-sec').hidden = false;
  $('render-out').innerHTML = '<div class="loading">Locking entities, transforming, verifying&hellip;</div>';
  $('prov-sec').hidden = true;

  const body = {
    alert_id: STATE.alertId,
    address: STATE.address,
    lang: $('lang').value,
    target_grade: parseFloat($('grade').value),
    with_audio: true,
  };
  const corrupt = $('corrupt').value;
  if (corrupt) body.corrupt = corrupt;

  // Every cached alert has expired, so a real clock renders every demo as
  // "ended 2 days ago" and the countdown - the thing a household actually
  // needs - never appears. Replaying the clock at issue time shows the
  // countdown as it stood. The alert text, polygon and hashes are untouched;
  // only `now` moves, and the UI says so.
  if ($('clock').value === 'issue') {
    const alert = STATE.alerts.find((a) => a.id === STATE.alertId);
    if (alert && alert.sent) {
      body.as_of = new Date(new Date(alert.sent).getTime() + 60 * 1000).toISOString();
    }
  }

  let r;
  try {
    r = await api('api/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) {
    $('render-out').innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  STATE.render = r;
  paintRender(r);
  paintProvenance(r);
}

function paintRender(r) {
  const hh = r.household || {};
  const rel = (hh.relation || {});
  const dir = r.text_direction || 'ltr';

  const steps = r.steps || [];
  const body = (r.segments || []).filter((s) => s.role === 'description');
  const headline = (r.segments || []).find((s) => s.role === 'headline');

  const positionClass = rel.status === 'inside' ? 'inside' : rel.status === 'near_edge' ? 'near' : '';

  const corruptionStrip = r.corruption ? `
    <div class="danger-strip">
      ADVERSARIAL TEST INPUT &mdash; "${esc(r.corruption.cls)}" injected into segment
      ${esc(r.corruption.segment_id)} (${esc(r.corruption.note)}).<br>
      This is not a production artifact. Watch what the verifier does with it.
    </div>` : '';

  const instrNote = r.no_instructions_in_source ? `
    <div class="abstain-note" style="margin-bottom:12px">
      <strong>The source alert carried no instruction field.</strong>
      No actions are listed, because none were issued. This system does not infer
      actions and does not suggest any of its own.
    </div>` : '';

  $('render-out').innerHTML = `
    ${corruptionStrip}
    <div class="split">
      <div>
        <div class="pane-title">What the National Weather Service actually sent</div>
        <pre class="raw">${esc(r.source.headline || '')}

${esc(r.source.description || '(no description)')}

${r.source.instruction ? esc(r.source.instruction) : '(no instruction field)'}</pre>
        <div class="kv" style="margin-top:10px">
          <b>${esc(r.source.event)}</b> &middot; ${esc(r.source.senderName)}<br>
          ${esc(r.source.areaDesc)}
        </div>
        ${hh.geometry ? drawMap(hh) : '<div class="hint">This alert carries no polygon.</div>'}
      </div>

      <div dir="${dir}">
        <div class="pane-title" dir="ltr">
          The same alert, for this household
          <span class="spacer"></span>
          <span id="fk-badge"></span>
        </div>

        ${hh.plain_statement ? `
        <div class="position ${positionClass}">
          <div class="big">${esc(hh.plain_statement)}</div>
          <div class="sub">
            ${esc(rel.detail || '')} &middot; geometry: ${esc(rel.basis || 'none')}
            ${$('clock').value === 'issue'
              ? ' &middot; <span style="color:var(--warn)">clock replayed at issue time; alert text unchanged</span>'
              : ''}
          </div>
        </div>` : ''}

        ${headline ? segHtml(headline, true) : ''}
        ${instrNote}

        ${steps.length ? `
          <div class="pane-title" dir="ltr" style="margin-top:14px">What to do</div>
          <ol class="steps">${steps.map(stepHtml).join('')}</ol>` : ''}

        ${body.length ? `
          <div class="pane-title" dir="ltr" style="margin-top:16px">Details</div>
          <div>${body.map((s) => segHtml(s, false)).join('')}</div>` : ''}

        ${r.audio && r.audio.ok ? `
          <div class="pane-title" dir="ltr" style="margin-top:16px">
            Spoken &mdash; ${esc(r.audio.engine)}
          </div>
          <audio controls src="${esc(r.audio.url)}"></audio>
          ${r.audio.note ? `<div class="hint">${esc(r.audio.note)}</div>` : ''}
        ` : (r.audio ? `<div class="hint">Audio unavailable: ${esc(r.audio.reason)}</div>` : '')}
      </div>
    </div>

    <div class="row" style="margin-top:16px;font-size:12.5px;color:var(--ink-dim)">
      <span><b style="color:var(--ink)">${r.segment_count}</b> segments</span>
      <span><b style="color:var(--abstain)">${r.abstained_count}</b> abstained</span>
      <span><b style="color:var(--ink)">${r.entities_locked}</b> entities locked</span>
      <span><b style="color:var(--ink)">${r.elapsed_ms} ms</b></span>
      ${r.abstention_reasons.length
        ? `<span class="muted">reasons: ${esc(r.abstention_reasons.join(', '))}</span>` : ''}
    </div>`;

  paintFk(r);
}

function segHtml(s, big) {
  const abst = s.status === 'verbatim_abstained';
  return `<div class="seg ${abst ? 'abstained' : ''}">
    ${s.section_label ? `<span class="lab" dir="ltr">${esc(s.section_label)}</span>` : ''}
    <span class="txt" style="${big ? 'font-size:16px;font-weight:600' : ''}">${esc(s.output_text)}</span>
    ${abst ? `<div class="why" dir="ltr">${esc(abstainLabel(s.reason))}</div>` : ''}
  </div>`;
}

function stepHtml(s) {
  const abst = s.status === 'verbatim_abstained';
  const span = s.source_span;
  return `<li class="${abst ? 'abstained' : ''}">
    <div>${esc(s.output_text)}</div>
    ${span ? `<div class="cite" dir="ltr">
        <b>source:</b> instruction field, characters ${span[0]}&ndash;${span[1]}
      </div>` : ''}
    ${abst ? `<div class="abstain-note" dir="ltr">
        <strong>Original text shown &mdash; machine translation withheld.</strong>
        ${esc(abstainLabel(s.reason))}
        <span class="interp">If you need this in your language, ask for an interpreter:
          Virginia 2-1-1, or call your local emergency manager and say the name of your language.</span>
      </div>` : ''}
  </li>`;
}

function abstainLabel(reason) {
  const map = {
    entity_integrity: 'A locked value (a number, road, time or place) did not survive the transformation intact.',
    translation_completeness: 'Too much of the English text survived untranslated for this to be a usable translation.',
    semantic_fidelity: 'The round trip back to English drifted too far from the source.',
    instruction_coverage: 'The instruction did not survive intact — typically a lost or inverted negation.',
    grounding: 'The output asserted something the source does not say.',
    verification_unavailable: 'A verification check could not run, so the system abstained rather than assume it passed.',
  };
  if (!reason) return '';
  if (reason.startsWith('content_safety')) return 'The output guard rejected this render.';
  return map[reason] || reason;
}

function paintFk(r) {
  // Flesch-Kincaid is an English formula. Computing it on the target text
  // would be meaningless, so the badge is shown for English renders and
  // otherwise labelled as describing the English the translation came from.
  const el = $('fk-badge');
  if (!el) return;
  const srcText = [r.source.description, r.source.instruction].filter(Boolean).join(' ');
  const outText = (r.segments || []).map((s) => s.output_text).join(' ');
  const a = fkGrade(srcText), b = fkGrade(outText);
  if (a == null || b == null) { el.textContent = ''; return; }
  const note = r.language === 'en' ? '' : ' (English source only)';
  el.innerHTML = `<span class="fk">
      <span class="from">FK ${a.toFixed(1)}</span>
      <span class="arrow">&rarr;</span>
      <span class="to">${b.toFixed(1)}</span>
      <span class="muted">${esc(note)}</span>
    </span>`;
}

/* Flesch-Kincaid grade, client side, for the live badge only. The numbers that
 * go in the deck come from eval/metrics.py using textstat, not from here. */
function fkGrade(text) {
  if (!text) return null;
  const words = text.match(/[A-Za-z']+/g) || [];
  const sentences = (text.match(/[.!?]+/g) || []).length || 1;
  if (words.length < 20) return null;
  let syll = 0;
  for (const w of words) syll += countSyllables(w.toLowerCase());
  return 0.39 * (words.length / sentences) + 11.8 * (syll / words.length) - 15.59;
}
function countSyllables(w) {
  w = w.replace(/(?:[^laeiouy]es|ed|[^laeiouy]e)$/, '').replace(/^y/, '');
  const m = w.match(/[aeiouy]{1,2}/g);
  return m ? m.length : 1;
}

/* --------------------------------------------------------------------- map */

function drawMap(hh) {
  const geom = hh.geometry, g = hh.geocode, rel = hh.relation || {};
  if (!geom || !g) return '';
  const rings = [];
  const collect = (coords, depth) => {
    if (depth === 1) rings.push(coords);
    else coords.forEach((c) => collect(c, depth - 1));
  };
  if (geom.type === 'Polygon') geom.coordinates.forEach((r) => rings.push(r));
  else if (geom.type === 'MultiPolygon') geom.coordinates.forEach((p) => p.forEach((r) => rings.push(r)));
  if (!rings.length) return '';

  const pts = rings.flat().concat([[g.lon, g.lat]]);
  if (rel.nearest_edge) pts.push(rel.nearest_edge);
  let minX = Math.min(...pts.map((p) => p[0])), maxX = Math.max(...pts.map((p) => p[0]));
  let minY = Math.min(...pts.map((p) => p[1])), maxY = Math.max(...pts.map((p) => p[1]));
  const padX = (maxX - minX) * 0.12 || 0.02, padY = (maxY - minY) * 0.12 || 0.02;
  minX -= padX; maxX += padX; minY -= padY; maxY += padY;

  const W = 560, H = 380;
  // Latitude correction so the shape is not stretched at Virginia's latitude.
  const midLat = (minY + maxY) / 2;
  const kx = Math.cos(midLat * Math.PI / 180);
  const spanX = (maxX - minX) * kx, spanY = maxY - minY;
  const scale = Math.min(W / spanX, H / spanY);
  const offX = (W - spanX * scale) / 2, offY = (H - spanY * scale) / 2;
  const X = (lon) => offX + (lon - minX) * kx * scale;
  const Y = (lat) => H - offY - (lat - minY) * scale;

  const paths = rings.map((r) =>
    `<path d="${r.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('')}Z"
       fill="#8b1a1a" fill-opacity="0.14" stroke="#8b1a1a" stroke-width="1.6"/>`).join('');

  const px = X(g.lon), py = Y(g.lat);
  const edge = rel.nearest_edge
    ? `<line x1="${px.toFixed(1)}" y1="${py.toFixed(1)}"
             x2="${X(rel.nearest_edge[0]).toFixed(1)}" y2="${Y(rel.nearest_edge[1]).toFixed(1)}"
             stroke="#0d132d" stroke-width="1.2" stroke-dasharray="4 3"/>
       <text x="${((px + X(rel.nearest_edge[0])) / 2).toFixed(1)}"
             y="${((py + Y(rel.nearest_edge[1])) / 2 - 6).toFixed(1)}"
             fill="#0d132d" font-size="11" font-family="Instrument Sans, sans-serif" letter-spacing="0.6" text-anchor="middle">
         ${rel.distance_km} km</text>` : '';

  // Scale bar: 10 km in projected units.
  const kmPerDegLon = 111.32 * kx;
  const barPx = (10 / kmPerDegLon) * kx * scale;
  const bar = barPx > 20 && barPx < W * 0.6 ? `
    <g transform="translate(14,${H - 20})">
      <line x1="0" y1="0" x2="${barPx.toFixed(1)}" y2="0" stroke="#87836f" stroke-width="2"/>
      <text x="${(barPx / 2).toFixed(1)}" y="-6" fill="#87836f" font-size="10"
            font-family="Instrument Sans, sans-serif" letter-spacing="0.6" text-anchor="middle">10 km</text>
    </g>` : '';

  return `
    <svg class="map" viewBox="0 0 ${W} ${H}" style="margin-top:12px" role="img"
         aria-label="Warning polygon with the household position marked">
      <rect width="${W}" height="${H}" fill="#e4eaf1"/>
      ${paths}${edge}${bar}
      <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="7" fill="#0d132d"
              stroke="#ffffff" stroke-width="2"/>
      <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="13" fill="none"
              stroke="#0d132d" stroke-opacity="0.4" stroke-width="1"/>
    </svg>
    <div class="legend">
      <span><i style="background:#8b1a1a;opacity:.45"></i>warning polygon</span>
      <span><i style="background:#0d132d"></i>your address</span>
      <span><i style="background:#0d132d;opacity:.45"></i>distance to nearest edge</span>
      <span class="muted">drawn from the alert's own geometry &middot; no tile server</span>
    </div>`;
}

/* -------------------------------------------------------------- provenance */

function paintProvenance(r) {
  const m = r.manifest;
  $('prov-sec').hidden = false;
  $('prov-out').innerHTML = `
    <div class="split">
      <div>
        <div class="pane-title">Manifest</div>
        <div class="kv" style="margin-bottom:10px">
          <b>source sha256</b> ${esc(m.source.sha256)}<br>
          <b>sender</b> ${esc(m.source.sender)}<br>
          <b>sent</b> ${esc(m.source.sent)} &middot; <b>fetched</b> ${esc(m.source.fetched_at)}<br>
          <b>transport</b> ${esc(m.source.transport)}<br>
          <b>signature</b> ${esc(m.signature.algorithm)} &middot; key ${esc(m.signature.key_id)}<br>
          <b>render digest</b> ${esc(m.render.digest_sha256)}
        </div>
        <div class="row">
          <button id="verify-btn">Verify this manifest</button>
          <button class="ghost" id="tamper-btn">Tamper with it, then verify</button>
          <button class="ghost" id="copy-btn">Copy JSON</button>
        </div>
        <div id="verify-out" style="margin-top:12px"></div>
      </div>
      <div>
        <div class="pane-title">Transform chain</div>
        <pre class="json">${esc(JSON.stringify(m.transform_chain, null, 2))}</pre>
        <div class="limits">
          <h3>What a valid manifest does and does not prove</h3>
          <ul style="margin:0;padding-left:18px">
            ${m.limitations.map((l) => `<li>${esc(l)}</li>`).join('')}
          </ul>
        </div>
      </div>
    </div>`;

  $('verify-btn').onclick = () => runVerify(m, r.segments);
  $('tamper-btn').onclick = () => {
    // Flip an abstained segment to "verified" without re-signing: exactly what
    // an attacker editing a downloaded artifact would try.
    const tampered = JSON.parse(JSON.stringify(m));
    const victim = tampered.segments.find((s) => s.status === 'verbatim_abstained')
      || tampered.segments[0];
    victim.status = 'translated_verified';
    delete victim.reason;
    runVerify(tampered, r.segments, 'Manifest edited in the browser: one segment’s status was '
      + 'flipped from abstained to verified, with the original signature left in place.');
  };
  $('copy-btn').onclick = () => {
    navigator.clipboard.writeText(JSON.stringify(m, null, 2));
    $('copy-btn').textContent = 'Copied';
    setTimeout(() => ($('copy-btn').textContent = 'Copy JSON'), 1400);
  };
}

async function runVerify(manifest, segments, note) {
  $('verify-out').innerHTML = '<div class="loading">Verifying&hellip;</div>';
  let v;
  try {
    v = await api('api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifest, rendered_segments: segments }),
    });
  } catch (e) {
    $('verify-out').innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  $('verify-out').innerHTML = `
    ${note ? `<div class="danger-strip">${esc(note)}</div>` : ''}
    <div class="verdict" style="color:${v.valid ? 'var(--ok)' : 'var(--bad)'}">
      ${v.valid ? 'MANIFEST VALID' : 'MANIFEST INVALID'}
    </div>
    <table class="checks">
      ${v.checks.map((c) => `<tr>
        <td class="s ${c.passed ? 'ok' : 'bad'}">${c.passed ? 'PASS' : 'FAIL'}</td>
        <td class="n">${esc(c.name)}</td>
        <td>${esc(c.detail)}</td>
      </tr>`).join('')}
    </table>
    <div class="hint">${esc(v.what_this_proves)}</div>`;
}

/* ------------------------------------------------------------------- wire */

$('find').onclick = findAlerts;
$('addr').addEventListener('keydown', (e) => { if (e.key === 'Enter') findAlerts(); });
$('rerender').onclick = doRender;
$('lang').onchange = doRender;
$('grade').onchange = doRender;
$('corrupt').onchange = doRender;
$('clock').onchange = doRender;

loadHealth();
