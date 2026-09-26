/* Last-Mile Assist front end. Vanilla JS, no build step.
 *
 * Rendering rule: every sentence about a program is drawn from a segment whose
 * citation points into a cached FEMA / eCFR / SBA / SAMHSA page. This file
 * never writes program facts of its own; the only prose it adds is layout
 * labels ("What it is", "How to apply").
 */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (path, opts = {}) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const r = await fetch(path, { ...opts, signal: controller.signal });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || `${r.status} ${r.statusText}`);
    return body;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('The service is taking too long. Please try again, or use the official help numbers below.');
    throw error;
  } finally { clearTimeout(timer); }
};
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) });
const coreApi = async (path, options = {}) => {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
  return body;
};

let STATE = { pick: null, last: null, request: 0 };

function optionsFallback(error) {
  const county = STATE.pick ? 'the county you selected' : 'your selected location';
  const needs = selectedNeeds();
  const needText = needs.length ? `Your selected needs are still saved on this page (${needs.map(esc).join(', ')}).` : '';
  return `<div class="err" role="alert"><strong>We could not finish checking your options.</strong>
    <p>${esc(error.message || 'The service is temporarily unavailable.')} ${needText}</p>
    <p>For verified help now: call <strong>FEMA at 800-621-3362</strong>, call <strong>Virginia 211</strong> by dialing 211, or call 911 if anyone is in immediate danger. Tell them you need help for ${county}.</p>
    <button type="button" id="retry-options">Try again</button>
    <p class="hint">This page did not make an eligibility decision. It will retry the same county and needs.</p></div>`;
}

const KIND_LABEL = {
  what: 'What it is', who: 'Who can get it', documents: 'What to have ready',
  how_to_apply: 'How to apply', deadline: 'Deadline', contact: 'Who to call', privacy: 'Privacy',
};
const AVAIL_LABEL = {
  likely: 'DECLARED FOR YOUR COUNTY', late: 'LATE WINDOW OPEN', closed: 'CLOSED',
  check: 'MAY BE AVAILABLE - CONFIRM', always: 'AVAILABLE NOW', unavailable: 'NOT DECLARED HERE',
};
const WITHHELD = 'Original English shown - translation withheld because it could not be verified.';

function replayLabel(r) {
  if (!$('clock').value || !r.as_of) return '';
  const date = new Date(r.as_of);
  const readable = Number.isNaN(date.getTime()) ? r.as_of.slice(0, 10)
    : date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  return `<span class="history-label">Historical replay: ${esc(readable)}</span>`;
}

function actionPlan(r, segs) {
  const program = (r.programs || []).find((item) => ['likely', 'late', 'always', 'check'].includes(item.availability));
  if (!program) return '';
  const name = segs[program.name_segment]?.output_text || 'disaster assistance';
  const claims = (program.claim_segments || []).map((id) => segs[id]).filter(Boolean);
  const document = claims.find((item) => item.meta?.claim_kind === 'documents');
  const canApply = ['likely', 'late'].includes(program.availability);
  return `<div class="action-plan" dir="ltr">
    <div class="action-plan-head"><div><div class="kind">Start here</div><h3>Your next three steps</h3></div>${replayLabel(r)}</div>
    <ol>
      <li><strong>${canApply ? 'Start your application' : 'Confirm what is open'}.</strong> ${canApply
        ? `Use <a href="https://www.disasterassistance.gov/" target="_blank" rel="noopener">DisasterAssistance.gov</a> for ${esc(name)}.`
        : `Call FEMA at <a href="tel:18006213362">800-621-3362</a> and ask about ${esc(name)}.`}</li>
      <li><strong>Get your information ready.</strong> ${document ? esc(document.output_text) : 'Gather insurance information and records of disaster damage you already have.'}</li>
      <li><strong>Get help if you get stuck.</strong> Call FEMA at <a href="tel:18006213362">800-621-3362</a> or dial <a href="tel:211">211</a> in Virginia. Say: “I am in ${esc(r.county.name)} and need help with ${esc((r.needs || []).join(' and ').replaceAll('_', ' '))}.”</li>
    </ol>
    <p class="hint">FEMA makes the eligibility decision. Detailed requirements and exact source evidence are below.</p>
  </div>`;
}

/* ------------------------------------------------------------------ setup */

async function init() {
  const pageParameters = new URLSearchParams(window.location.search);
  if (pageParameters.get('mode') === 'citizen') {
    $('clock').value = '';
    $('clock').hidden = true;
    $('corrupt').value = '';
    $('corrupt').hidden = true;
    if ($('corrupt').previousElementSibling) $('corrupt').previousElementSibling.hidden = true;
  }
  try {
    const h = await api('api/health');
    const live = h.providers.translator.startsWith('azure');
    const b = $('engine-badge');
    b.className = 'badge ' + (live ? 'live' : 'local');
    b.textContent = live ? 'AZURE LIVE' : 'LOCAL FALLBACK ENGINES';
    $('lang').innerHTML = '<option value="en">English</option>' + Object.entries(h.languages)
      .map(([k, v]) => `<option value="${esc(k)}">${esc(v.name)}</option>`).join('');
    const requestedLanguage = pageParameters.get('lang');
    if ([...$('lang').options].some((option) => option.value === requestedLanguage)) {
      $('lang').value = requestedLanguage;
      document.documentElement.lang = requestedLanguage === 'prs' ? 'fa' : requestedLanguage;
      document.documentElement.dir = ['ar', 'prs'].includes(requestedLanguage) ? 'rtl' : 'ltr';
    }
  } catch (e) { $('engine-badge').textContent = 'API unreachable'; }

  const n = await api('api/assist/needs');
  $('needs').innerHTML = n.needs.map((x) => `
    <label class="need"><input type="checkbox" value="${esc(x.code)}"
      ${['home_damaged', 'cant_stay_home'].includes(x.code) ? 'checked' : ''}> ${esc(x.label)}</label>`).join('');
}

function selectedNeeds() {
  return [...document.querySelectorAll('#needs input:checked')].map((i) => i.value);
}

function selectedPlanNeeds() {
  return [...document.querySelectorAll('input[name="plan-need"]:checked')].map((input) => input.value);
}

function planActions(packet) {
  return (packet.actions || []).map((action) => `<li>${esc(action.label)}${action.current_limit ? `<div class="hint">${esc(action.current_limit)}</div>` : ''}</li>`).join('');
}

function planResult(packet, resumed = false) {
  const code = packet.continuity?.code;
  if (!code) return `<div class="err">This plan could not be created. Please check the requested details.</div>`;
  return `<div class="kind">${resumed ? 'Resumed' : 'Created'} recovery plan</div>
    <div class="plan-code">${esc(code)}</div>
    <p class="hint">Keep this code. It expires in ${esc(packet.continuity.expires_in_hours)} hours and contains no name, address, phone number, or sensitive handoff reason.</p>
    <ol>${planActions(packet)}</ol>
    <div class="plan-actions">
      <button type="button" data-plan-verify>Verify plan</button>
      <button type="button" class="ghost" data-plan-download>Save offline copy</button>
    </div>
    <div class="plan-actions call-controls">
      <input type="tel" data-plan-phone placeholder="Your verified test phone number" aria-label="Verified test phone number">
      <label class="need"><input type="checkbox" data-plan-consent> I consent to this one call or text.</label>
      <button type="button" class="ghost" data-plan-call>Call with Microsoft voice</button>
      <button type="button" class="ghost" data-plan-sms>Send plan by text</button>
    </div>
    <div data-plan-message aria-live="polite"></div>`;
}

function bindPlan(packet) {
  const root = $('plan-result');
  const message = root.querySelector('[data-plan-message]');
  root.querySelector('[data-plan-verify]').onclick = async () => {
    message.textContent = 'Verifying…';
    try { const result = await coreApi('/api/packet/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ packet }) });
      message.textContent = result.valid ? 'Plan signature verified.' : 'This plan does not verify.';
    } catch (error) { message.textContent = error.message; }
  };
  root.querySelector('[data-plan-download]').onclick = async () => {
    try {
      const response = await fetch(`/api/packet/offline/${encodeURIComponent(packet.continuity.code)}`);
      if (!response.ok) throw new Error('Offline copy is unavailable.');
      const blob = await response.blob(); const link = document.createElement('a');
      link.href = URL.createObjectURL(blob); link.download = `${packet.continuity.code}-signed-snapshot.json`; link.click(); URL.revokeObjectURL(link.href);
      message.textContent = 'Signed offline copy downloaded.';
    } catch (error) { message.textContent = error.message; }
  };
  for (const [selector, path] of [['[data-plan-call]', '/api/calls/start'], ['[data-plan-sms]', '/api/sms/send']]) {
    root.querySelector(selector).onclick = async () => {
      const phone = root.querySelector('[data-plan-phone]').value.trim();
      const consent = root.querySelector('[data-plan-consent]').checked;
      if (!phone || !consent) { message.textContent = 'Enter your verified test number and confirm consent first.'; return; }
      message.textContent = 'Sending request…';
      try { const result = await coreApi(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ continuity_code: packet.continuity.code, phone_number: phone, consent }) });
        message.textContent = result.detail || result.status || 'Request accepted.';
      } catch (error) { message.textContent = error.message; }
    };
  }
}

async function createPlan(event) {
  event.preventDefault();
  const profile = { location: $('plan-location').value.trim(), jurisdiction: $('plan-county').value.trim() || null,
    needs: selectedPlanNeeds(), circumstances: [], context_reviewed: $('plan-context').checked };
  $('plan-result').innerHTML = '<div class="loading">Creating a signed plan…</div>';
  try {
    const result = await coreApi('/api/packet', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(profile) });
    if (result.status !== 'complete') throw new Error(result.question?.label || result.notice || 'More information is needed to create a plan.');
    $('plan-result').innerHTML = planResult(result.packet); bindPlan(result.packet);
  } catch (error) { $('plan-result').innerHTML = `<div class="err" role="alert">${esc(error.message)}</div>`; }
}

async function resumePlan(event) {
  event.preventDefault(); const code = $('resume-code').value.trim().toUpperCase();
  $('plan-result').innerHTML = '<div class="loading">Resuming plan…</div>';
  try { const result = await coreApi(`/api/continue/${encodeURIComponent(code)}`); $('plan-result').innerHTML = planResult(result.packet, true); bindPlan(result.packet); }
  catch (error) { $('plan-result').innerHTML = `<div class="err" role="alert">${esc(error.message)}</div>`; }
}

async function checkFraud(event) {
  event.preventDefault(); const output = $('fraud-result'); output.textContent = 'Checking…';
  try { const result = await coreApi('/api/fraud-check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: $('fraud-text').value }) });
    output.textContent = `${String(result.risk || 'unknown').toUpperCase()}: ${result.summary || result.message || 'Review the warning signs and use official contacts.'}`;
  } catch (error) { output.textContent = error.message; }
}

async function runChaos() {
  const output = $('chaos-result'); output.textContent = 'Running safe simulations…';
  try { const result = await coreApi('/api/chaos/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ modes: ['foundry_down', 'translator_down', 'maps_down', 'no_network'] }) });
    output.textContent = (result.outcomes || []).every((outcome) => outcome.safe) ? 'All simulated failures kept a safe fallback.' : 'A simulated fallback needs review.';
  } catch (error) { output.textContent = error.message; }
}

/* ------------------------------------------------------------------ request */

async function go() {
  const request = ++STATE.request;
  $('out-sec').hidden = false;
  $('prov-sec').hidden = true;
  $('out').innerHTML = '<div class="loading">Checking FEMA declarations and verifying every sentence&hellip;</div>';
  const body = {
    location: $('loc').value, needs: selectedNeeds(), text: $('text').value || null,
    danger_now: $('danger').checked, lang: $('lang').value,
    // Keep the first result fast. Speech can be requested separately in flows
    // that need it; it should never delay the primary assistance answer.
    with_audio: false,
    pick_fips: STATE.pick, as_of: $('clock').value || null,
  };
  if ($('corrupt').value) body.corrupt = $('corrupt').value;
  let r;
  try { r = await post('api/assist', body); }
  catch (e) {
    if (request === STATE.request) {
      $('out').innerHTML = optionsFallback(e);
      $('retry-options').onclick = () => go();
    }
    return;
  }
  if (request !== STATE.request) return;
  STATE.last = r;
  paint(r);
}

/* ------------------------------------------------------------------ render */

function paint(r) {
  const segs = Object.fromEntries((r.segments || []).map((s) => [s.id, s]));
  const byRole = (role) => (r.segments || []).filter((s) => s.role === role);
  const dir = r.text_direction || 'ltr';
  let html = '';

  if (r.corruption) {
    html += `<div class="danger-strip">ADVERSARIAL TEST INPUT &mdash; "${esc(r.corruption.cls)}" injected into
      segment ${esc(r.corruption.segment_id)} (${esc(r.corruption.note)}). Watch what the verifier does with it.</div>`;
  }
  if (r.privacy && r.privacy.notice) html += `<div class="notice info"><strong>Privacy</strong>${esc(r.privacy.notice)}</div>`;

  // Human first, when it matters. Above the answer, above everything.
  const e = r.escalation || {};
  if (e.level && e.level !== 'none') {
    const cls = e.level === 'urgent' ? '' : (e.human_first ? 'sensitive' : 'soft');
    const title = e.level === 'urgent' ? 'Get help from a person now'
      : (e.human_first ? 'Talk to a person about this' : 'A person can help with this');
    const reasons = byRole('escalation');
    const channels = byRole('channel');
    html += `<div class="handoff ${cls}" dir="${dir}">
      <h3 dir="ltr">${esc(title)}</h3>
      <div class="kind" dir="ltr">Why</div>${reasons.map((s) => `<div>${esc(s.output_text)}</div>`).join('')}
      <div class="kind" dir="ltr">Who to contact</div>
      ${channels.map((s) => `<div class="channel"><b dir="ltr">${esc(s.meta.label)}</b>
        <div>${esc(s.output_text)}${citeHtml(s)}</div></div>`).join('')}
      <div class="kind" dir="ltr">What to say</div>
      <div dir="ltr">“I am in ${esc((r.county || {}).name || 'Virginia')} and need help with ${esc((r.needs || []).join(' and ').replaceAll('_', ' '))}.”</div>
      <p class="hint" dir="ltr">This is a referral. This site does not transfer your call or send your information.</p>
    </div>`;
  }

  // Location needs a choice: ask, never guess.
  if (r.needs_location_choice) {
    html += `<div class="status late"><div class="big">${esc(r.location.note)}</div>
      <div class="row" style="margin-top:10px">${r.location.candidates.map((c) =>
        `<button class="ghost pick" data-f="${esc(c.county_fips)}">${esc(c.county_name)}
         <span class="muted">${c.share != null ? Math.round(c.share * 100) + '% of this ZIP' : ''}</span></button>`).join('')}</div>
      <div class="hint">${esc(r.location.source)}. Help is decided county by county, so we ask instead of guessing.</div></div>`;
    $('out').innerHTML = html;
    document.querySelectorAll('.pick').forEach((b) => b.onclick = () => { STATE.pick = b.dataset.f; go(); });
    return;
  }
  if (!r.county) {
    html += `<div class="err">${esc((r.location || {}).note || 'We could not find that place.')}</div>`;
    $('out').innerHTML = html;
    return;
  }

  // The answer.
  const d = (r.declarations || {}).primary;
  const w = d ? d.window : null;
  const state = w ? w.state : 'none';
  const chip = !w ? '<span class="chip none">NO DECLARATION</span>'
    : state === 'open' ? `<span class="chip open">${w.days_left} DAYS LEFT TO APPLY</span>`
    : state === 'late' ? `<span class="chip late">LATE WINDOW: ${w.late_days_left} DAYS</span>`
    : state === 'closed' ? '<span class="chip closed">DEADLINE PASSED</span>'
    : '<span class="chip none">NO INDIVIDUAL ASSISTANCE</span>';
  const statusSeg = byRole('status')[0];
  html += actionPlan(r, segs);
  html += `<div class="status ${state === 'open' ? 'open' : state === 'late' ? 'late' : ''}" dir="${dir}">
    <div dir="ltr" style="margin-bottom:8px">${chip}${replayLabel(r)}<span class="muted" style="font-size:12.5px">${esc(r.county.name)}
      &middot; FIPS ${esc(r.county.fips)}</span></div>
    ${statusSeg ? `<div class="big">${esc(statusSeg.output_text)}</div>${withheld(statusSeg)}` : ''}
    ${byRole('notice').filter((s) => s.meta.kind === 'deadline_caveat').map((s) => `<div class="hint">${esc(s.output_text)}</div>`).join('')}
    ${byRole('claim').filter((s) => s.meta.rule).map(claimHtml).join('')}
    <div class="row" dir="ltr" style="margin-top:10px;font-size:13.5px">
      <a href="https://www.disasterassistance.gov/" target="_blank" rel="noopener">Apply at DisasterAssistance.gov</a>
      <span class="muted">&middot;</span>
      <a href="https://egateway.fema.gov/ESF6/DRCLocator" target="_blank" rel="noopener">Find an open Disaster Recovery Center (FEMA)</a>
      <span class="muted" style="font-size:12px">&mdash; linked, not copied: centers open and close daily</span>
    </div>
    <div class="hint" dir="ltr">From OpenFEMA DisasterDeclarationsSummaries &middot; Individual Assistance =
      ihProgramDeclared OR iaProgramDeclared, per FEMA's data dictionary${$('clock').value
        ? ' &middot; <span style="color:var(--warn)">clock replayed to ' + esc(r.as_of.slice(0, 10)) + '; data unchanged</span>' : ''}</div>
  </div>`;

  // Suggestions from free text: offered, never applied silently.
  if ((r.suggested_needs || []).length) {
    html += `<div class="suggest" style="margin-bottom:14px"><span class="muted" style="font-size:13px">From what you wrote, you may also want:</span>
      ${r.suggested_needs.map((n) => `<button data-n="${esc(n.code)}">+ ${esc(n.label)}</button>`).join(' ')}</div>`;
  }

  // Programs.
  for (const p of r.programs || []) {
    const nameSeg = segs[p.name_segment], stSeg = segs[p.status_segment];
    const claims = p.claim_segments.map((id) => segs[id]);
    const groups = {};
    claims.forEach((c) => (groups[c.meta.claim_kind] = groups[c.meta.claim_kind] || []).push(c));
    html += `<div class="prog" dir="${dir}">
      <h4>${esc(nameSeg.output_text)}<span class="avail ${esc(p.availability)}" dir="ltr">${esc(AVAIL_LABEL[p.availability])}</span></h4>
      <div class="muted" style="font-size:13px" dir="ltr">${esc(p.agency)}${p.status_independent
        ? ' &middot; <span style="color:var(--ok)">available regardless of immigration status (FEMA)</span>' : ''}</div>
      <div style="margin-top:6px">${esc(stSeg.output_text)}</div>
      ${p.gate_note && p.availability !== 'likely' ? `<div class="hint" dir="ltr">${esc(p.gate_note)}</div>` : ''}
      <details class="program-evidence"><summary>Requirements and source evidence</summary>
        ${['what', 'who', 'documents', 'deadline', 'how_to_apply', 'contact', 'privacy'].filter((k) => groups[k]).map((k) =>
          `<div class="kind" dir="ltr">${esc(KIND_LABEL[k])}</div>${groups[k].map(claimHtml).join('')}`).join('')}
      </details>
    </div>`;
  }

  // Status notes (citizenship), emphasised when the person raised it.
  const notes = byRole('status_note');
  if (notes.length) {
    const open = notes.some((s) => s.meta.emphasized);
    html += `<details ${open ? 'open' : ''} class="prog"><summary style="cursor:pointer;font-weight:600">
      Citizenship and immigration status &mdash; what FEMA says</summary>${notes.map(claimHtml).join('')}</details>`;
  }

  // FEMA's own fraud warnings.
  const fraud = byRole('fraud');
  if (fraud.length) {
    html += `<div class="fraud" dir="${dir}"><div class="kind" style="margin-top:0;color:var(--red)" dir="ltr">
      Protect yourself from disaster fraud &mdash; FEMA's own warnings</div>
      <ul style="margin:6px 0 0;padding-left:18px">${fraud.map((s) => `<li>${claimInner(s)}</li>`).join('')}</ul></div>`;
  }

  const lang = byRole('notice').find((s) => s.meta.kind === 'language_need');
  if (lang) html += `<div class="hint" style="margin-top:12px">${claimInner(lang)}</div>`;

  if (r.audio && r.audio.ok) {
    html += `<div class="kind">Spoken &mdash; ${esc(r.audio.engine)}</div><audio controls src="${esc(r.audio.url)}"></audio>`;
  }

  const reasons = (r.abstention_reasons || []).join(', ');
  html += `<details class="technical-details"><summary>Technical verification details</summary>
    <div class="row" style="margin-top:14px;font-size:12.5px;color:var(--ink-dim)">
      <span><b style="color:var(--ink)">${r.segment_count}</b> source passages</span>
      <span><b style="color:var(--abstain)">${r.abstained_count}</b> transformations withheld</span>
      <span><b style="color:var(--ink)">${(r.sources_used || []).length}</b> sources cited</span>
      <span><b style="color:var(--ink)">${r.elapsed_ms} ms</b></span>
    </div>${reasons ? `<p class="hint">Safeguards used original source text for: ${esc(reasons)}.</p>` : '<p class="hint">English source text was retained unchanged.</p>'}</details>`;

  $('out').innerHTML = html;
  document.querySelectorAll('.suggest button').forEach((b) => b.onclick = () => {
    const box = document.querySelector(`#needs input[value="${b.dataset.n}"]`);
    if (box) box.checked = true;
    go();
  });
  if (r.manifest) paintProvenance(r);
}

function withheld(s) {
  return '';
}

function citeHtml(s) {
  const c = (s.meta || {}).citation;
  if (!c) return '';
  return `<div class="cite" dir="ltr">${esc(c.publisher)} &middot; <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>
    &middot; chars ${c.start}&ndash;${c.end}</div>
    ${s.status === 'translated_verified' && s.output_text !== s.source_text
      ? `<details class="exact" dir="ltr"><summary>exact words</summary><blockquote>${esc(c.quote)}</blockquote></details>` : ''}`;
}

function claimInner(s) {
  return `${esc(s.output_text)}${withheld(s)}${citeHtml(s)}`;
}

function claimHtml(s) {
  return `<div class="claim ${s.status === 'verbatim_abstained' ? 'abstained' : ''}">${claimInner(s)}</div>`;
}

/* -------------------------------------------------------------- provenance */

function paintProvenance(r) {
  const m = r.manifest;
  $('prov-sec').hidden = false;
  $('prov').innerHTML = `
    <div class="kv" style="margin-bottom:10px">
      ${m.sources.map((s) => `<b>${esc(s.id)}</b> ${esc(s.retrieval)} &middot; sha256 ${esc((s.sha256 || '').slice(0, 16))}&hellip;
        &middot; <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)}</a>`).join('<br>')}
      <br><b>declarations</b> ${esc(m.data.dataset)} &middot; sha256 ${esc((m.data.sha256 || '').slice(0, 16))}&hellip; &middot; fetched ${esc(m.data.fetched_at)}
      <br><b>what we kept about you</b> county ${esc(m.retained.county_fips)} &middot; needs [${esc((m.retained.needs || []).join(', '))}]
        &middot; not kept: ${esc(m.retained.not_retained)}
      <br><b>signature</b> ${esc(m.signature.algorithm)} &middot; key ${esc(m.signature.key_id)}
    </div>
    <div class="row">
      <button id="verify-btn">Verify this page</button>
      <button class="ghost" id="tamper-btn">Tamper with it, then verify</button>
    </div>
    <div id="verify-out" style="margin-top:12px"></div>
    <div class="accordion">
      <button class="accordion-head" type="button" aria-expanded="false">What a valid manifest does and does not prove</button>
      <div class="accordion-body" hidden>
        <ul style="margin:0;padding-left:20px">${m.limitations.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>
      </div>
    </div>`;
  $('verify-btn').onclick = () => verify(m, r.segments);
  $('tamper-btn').onclick = () => {
    // Change one word inside a cited FEMA quote on the page, keep the manifest:
    // exactly what an edited screenshot or forwarded copy would do.
    const segs = JSON.parse(JSON.stringify(r.segments));
    const victim = segs.find((s) => s.role === 'fraud') || segs[0];
    victim.output_text = victim.output_text.replace(/never/i, 'sometimes');
    victim.source_text = victim.source_text.replace(/never/i, 'sometimes');
    verify(m, segs, 'One cited FEMA sentence on this page was edited ("never" became "sometimes"), manifest left as issued.');
  };
}

async function verify(manifest, segments, note) {
  $('verify-out').innerHTML = '<div class="loading">Verifying&hellip;</div>';
  let v;
  try { v = await post('api/verify', { manifest, rendered_segments: segments }); }
  catch (e) { $('verify-out').innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  $('verify-out').innerHTML = `${note ? `<div class="danger-strip">${esc(note)}</div>` : ''}
    <div class="verdict" style="color:${v.valid ? 'var(--ok)' : 'var(--bad)'}">
      ${v.valid ? 'PAGE VERIFIED' : 'PAGE DOES NOT VERIFY'}</div>
    <table class="checks">${v.checks.map((c) => `<tr><td class="s ${c.passed ? 'ok' : 'bad'}">${c.passed ? 'PASS' : 'FAIL'}</td>
      <td class="n">${esc(c.name)}</td><td>${esc(c.detail)}</td></tr>`).join('')}</table>`;
}

/* ------------------------------------------------------------------- wire */

$('go').onclick = () => { STATE.pick = null; go(); };
// The location field sits in the topper, so its submit button has to reach the
// same handler as the one at the bottom of step 2.
$('hero-go').onclick = () => { STATE.pick = null; go(); };
$('loc').addEventListener('keydown', (e) => { if (e.key === 'Enter') { STATE.pick = null; go(); } });
['lang', 'clock', 'corrupt'].forEach((id) => $(id).onchange = () => { if (STATE.last) go(); });
$('plan-form').addEventListener('submit', createPlan);
$('resume-plan-form').addEventListener('submit', resumePlan);
$('fraud-form').addEventListener('submit', checkFraud);
$('run-chaos').onclick = runChaos;
init();
