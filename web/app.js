const state = {
  step: 1,
  urgency: "safe_now",
  needs: new Set(),
  jurisdiction: null,
  packetChannel: "web",
  navigation: null,
  transform: null,
  alert: null,
  providers: {},
};

const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  return response;
};

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function showView(name) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "alert-lab" && !state.transform) runTransform();
}

function setStep(step) {
  state.step = step;
  $$(".form-step").forEach((panel) => panel.classList.toggle("active", Number(panel.dataset.formStep) === step));
  $$('[data-step-indicator]').forEach((item) => {
    const itemStep = Number(item.dataset.stepIndicator);
    item.classList.toggle("active", itemStep === step);
    item.classList.toggle("done", itemStep < step);
    const circle = $(":scope > span", item);
    circle.textContent = itemStep < step ? "✓" : String(itemStep);
  });
  $(".navigator-card").scrollIntoView({ behavior: "smooth", block: "center" });
}

function programIcon(category) {
  const icons = {
    "Immediate safety": "!", "Local help": "211", "Housing & essential needs": "⌂",
    Food: "⌑", "Repair & recovery": "⌂", "Lost work": "▣", Documents: "▧",
    "Emotional support": "♡", Legal: "⚖", Shelter: "⌂",
  };
  return icons[category] || "→";
}

function channelText(packet, channel) {
  const payload = packet.channels[channel];
  if (channel === "web") {
    return `${payload.status}\n${payload.deadline}\n\n${payload.steps.map((step, index) => `${index + 1}. ${step}`).join("\n")}`;
  }
  if (channel === "sms") return payload.text;
  if (channel === "voice") return payload.script;
  return payload.text;
}

function renderProtocol(protocol) {
  const target = $("#protocol-panel");
  if (!protocol || protocol.status !== "complete") {
    target.innerHTML = "";
    return;
  }
  const packet = protocol.packet;
  const audit = packet.question_audit;
  state.packet = packet;
  state.packetChannel = "web";
  target.innerHTML = `
    <section class="protocol-packet">
      <div class="historical-ribbon">HISTORICAL REPLAY · THE 2024 APPLICATION DEADLINE HAS PASSED · CONFIRM CURRENT HELP</div>
      <div class="packet-head"><div><p class="overline">DISASTER ACTION PACKET · ${escapeHtml(packet.protocol)}</p><h3>One verified state. Four resilient channels.</h3><p>${escapeHtml(packet.snapshot.notice)}</p></div><span class="proof-stamp">✓ PROOF ${escapeHtml(packet.proof.proof_id)}</span></div>
      <div class="packet-facts">
        <div><small>Jurisdiction</small><strong>${escapeHtml(packet.jurisdiction)}</strong></div>
        <div><small>Government ID</small><strong>${escapeHtml(packet.disaster.id)}</strong></div>
        <div><small>Snapshot</small><strong>${escapeHtml(packet.snapshot.as_of_label)}</strong></div>
        <div><small>Locked deadline</small><strong>${escapeHtml(packet.deadlines[0].value)} · passed</strong></div>
      </div>
      <div class="packet-body">
        <div>
          <div class="question-audit"><div><b>${audit.potential_question_groups}</b><span>possible groups</span></div><div><b>${audit.asked}</b><span>asked</span></div><div><b>${audit.skipped}</b><span>skipped</span></div></div>
          <div class="channel-tabs" role="tablist">${["web", "sms", "voice", "offline"].map((channel) => `<button type="button" role="tab" data-packet-channel="${channel}" class="${channel === "web" ? "active" : ""}">${channel.toUpperCase()}</button>`).join("")}</div>
          <div class="channel-preview" id="channel-preview">${escapeHtml(channelText(packet, "web"))}</div>
        </div>
        <aside class="continuity-card"><small>ANONYMOUS CROSS-CHANNEL CONTINUITY</small><div class="continuity-code">${escapeHtml(packet.continuity.code)}</div><p>Use <strong>${escapeHtml(packet.continuity.resume_command)}</strong> on a surviving channel. Expires in 24 hours. No name, street address, SSN, or documents.</p><button type="button" data-copy-code>Copy recovery command</button><button type="button" data-verify-packet style="margin-top:7px">Verify packet + channels</button><div class="sms-send"><label for="sms-number">Send this verified packet by SMS</label><input id="sms-number" type="tel" inputmode="tel" autocomplete="tel" placeholder="+15715550123" maxlength="16" /><label class="sms-consent"><input id="sms-consent" type="checkbox" /> I consent to one transactional message. Message and data rates may apply.</label><button type="button" data-send-sms>Send verified SMS</button><small>${state.providers.azure_communication_services_sms ? "Azure SMS is ready." : "Azure SMS is currently in preview mode."} Never use this for 911.</small></div></aside>
      </div>
    </section>`;
}

function fallbackMapSvg(geometry, location) {
  const polygon = geometry?.coordinates?.[0] || [];
  const points = [...polygon, [location.longitude, location.latitude]];
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const project = ([x, y]) => [20 + ((x - minX) / Math.max(.001, maxX - minX)) * 560, 135 - ((y - minY) / Math.max(.001, maxY - minY)) * 110];
  const path = polygon.map((point, index) => `${index ? "L" : "M"}${project(point).join(" ")}`).join(" ") + " Z";
  const pin = project([location.longitude, location.latitude]);
  return `<svg viewBox="0 0 600 155" role="img" aria-label="Fallback map showing the alert polygon and checked location"><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#d8e1dc" stroke-width="1"/></pattern></defs><rect width="600" height="155" fill="url(#grid)"/><path d="${path}" fill="rgba(233,109,56,.16)" stroke="#e96d38" stroke-width="3"/><circle cx="${pin[0]}" cy="${pin[1]}" r="7" fill="#063d3b" stroke="#d7f663" stroke-width="4"/></svg><span>Geometry fallback · Azure Maps activates when configured</span>`;
}

async function renderAlertMap(alertContext, location) {
  const target = $("#map-card");
  if (!target) return;
  target.innerHTML = fallbackMapSvg(alertContext.alert.geometry, location);
  try {
    const response = await api("/api/config");
    const config = await response.json();
    if (!config.azure_maps_key) return;
    if (!window.atlas) {
      await new Promise((resolve, reject) => {
        const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "https://atlas.microsoft.com/sdk/javascript/mapcontrol/3/atlas.min.css"; document.head.append(css);
        const script = document.createElement("script"); script.src = "https://atlas.microsoft.com/sdk/javascript/mapcontrol/3/atlas.min.js"; script.onload = resolve; script.onerror = reject; document.head.append(script);
      });
    }
    target.innerHTML = "";
    const map = new atlas.Map("map-card", { center: [location.longitude, location.latitude], zoom: 7, authOptions: { authType: "subscriptionKey", subscriptionKey: config.azure_maps_key } });
    map.events.add("ready", () => {
      const source = new atlas.source.DataSource(); map.sources.add(source);
      source.add(new atlas.data.Feature(new atlas.data.Polygon(alertContext.alert.geometry.coordinates)));
      source.add(new atlas.data.Feature(new atlas.data.Point([location.longitude, location.latitude])));
      map.layers.add(new atlas.layer.PolygonLayer(source, null, { fillColor: "rgba(233,109,56,.2)", fillOpacity: .7 }));
      map.layers.add(new atlas.layer.LineLayer(source, null, { strokeColor: "#e96d38", strokeWidth: 3 }));
      map.layers.add(new atlas.layer.BubbleLayer(source, null, { color: "#063d3b", radius: 7, strokeColor: "#d7f663", strokeWidth: 3 }));
    });
  } catch (_) {
    target.innerHTML = fallbackMapSvg(alertContext.alert.geometry, location);
  }
}

function renderResults(result) {
  state.navigation = result;
  const section = $("#results");
  section.hidden = false;
  $("#results-summary").textContent = `${result.recommendations.length} source-backed options for ${result.location}. Final eligibility is always decided by the agency.`;

  $("#urgent-panel").innerHTML = result.handoff.summary.urgency === "danger_now" ? `
    <div class="urgent-banner"><div><h3>Immediate danger comes first.</h3><p>Do not wait for this plan or collect documents.</p></div><a href="tel:911">Call 911</a></div>` : "";

  renderProtocol(result.protocol);

  const alert = result.alert_context.alert.properties;
  const position = result.alert_context.position;
  $("#alert-context").innerHTML = `
    <div class="alert-mark">!</div>
    <div><small>DEMO CAP FIXTURE · NOT A LIVE WARNING</small><h3>${escapeHtml(alert.event)}</h3><p>${escapeHtml(alert.headline)}</p></div>
    <div class="alert-position"><strong>${escapeHtml(position.status)}</strong><small>${escapeHtml(position.explanation)}</small></div>
    <div id="map-card" class="mini-map"></div>`;
  renderAlertMap(result.alert_context, result.location_match);

  $("#recommendation-list").innerHTML = result.recommendations.map((program, index) => `
    <article class="recommendation-card" data-program-id="${escapeHtml(program.id)}">
      <div class="recommendation-main">
        <div class="program-icon">${escapeHtml(programIcon(program.category))}</div>
        <div class="program-body">
          <div class="program-topline"><span class="category-pill">${index < 3 ? `Priority ${index + 1}` : escapeHtml(program.category)}</span><span class="confidence-pill">${escapeHtml(program.confidence.label)}</span></div>
          <h3>${escapeHtml(program.name)}</h3>
          <p>${escapeHtml(program.why)}</p>
          <p class="source-line">Source: <a href="${escapeHtml(program.source_url)}" target="_blank" rel="noopener">${escapeHtml(program.source_label)}</a> · ${escapeHtml(program.source_updated)}</p>
        </div>
        <div class="program-actions"><a href="${escapeHtml(program.apply_url)}" target="_blank" rel="noopener">${escapeHtml(program.apply_label)}</a><button type="button" data-details>What you’ll need +</button></div>
      </div>
      <div class="program-details">
        <div><h4>Who may qualify</h4><p>${escapeHtml(program.eligibility)}</p><p><strong>Important:</strong> ${escapeHtml(program.eligibility_notice)}</p></div>
        <div><h4>Information to gather</h4>${program.documents.length ? `<ul>${program.documents.map((doc) => `<li>${escapeHtml(doc)}</li>`).join("")}</ul>` : "<p>No documents needed for the first contact.</p>"}</div>
        <p class="alternative-note"><strong>If documents are gone:</strong> ${escapeHtml(program.document_alternatives)}</p>
      </div>
    </article>`).join("") || `<div class="recommendation-card"><div class="recommendation-main"><div class="program-body"><h3>No confident match yet</h3><p>${escapeHtml(result.empty_notice)}</p></div></div></div>`;

  $("#privacy-receipt").innerHTML = `
    <span class="receipt-status">${result.privacy.stored ? "◷ MINIMAL PACKET · 24 HOURS" : "✓ NOTHING SAVED SERVER-SIDE"}</span>
    <h3>Your privacy receipt</h3>
    <p>${escapeHtml(result.privacy.message)}</p>
    <p><strong>Used for matching</strong></p><ul>${result.privacy.used.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    ${result.privacy.stored_fields ? `<p><strong>Stored for continuity</strong></p><ul>${result.privacy.stored_fields.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
    <p><strong>Never requested</strong></p><ul>${result.privacy.not_requested.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;

  const handoff = result.handoff;
  const packetEscalation = result.protocol?.status === "complete" ? result.protocol.packet.escalation : null;
  $("#handoff-card").innerHTML = `
    <p class="overline">HUMAN HANDOFF</p><h3>${handoff.recommended ? "A person may help." : "Want a person anyway?"}</h3>
    <p>${handoff.reasons.length ? escapeHtml(handoff.reasons.join(" ")) : "You can take this short, non-sensitive summary to a 211 navigator."}</p>
    <div class="handoff-reference">${escapeHtml(handoff.reference)}</div>
    ${packetEscalation ? `<p><strong>Read this to the representative:</strong><br />${escapeHtml(packetEscalation.read_this)}</p>` : ""}
    <ul>${handoff.contacts.map((contact) => `<li><strong>${escapeHtml(contact.value)}</strong> — ${escapeHtml(contact.when)}</li>`).join("")}</ul>
    <a href="tel:211">Call Virginia 211</a>`;

  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function submitNavigator(event) {
  event.preventDefault();
  const button = $('#navigator-form button[type="submit"]');
  const prior = button.innerHTML;
  button.disabled = true;
  button.innerHTML = "Matching official programs…";
  const circumstances = $$("#context-grid input:checked").map((input) => input.value);
  const housing = circumstances.includes("renter") ? "renter" : circumstances.includes("homeowner") ? "homeowner" : null;
  try {
    const response = await api("/api/navigate", {
      method: "POST",
      body: JSON.stringify({
        location: $("#location").value,
        jurisdiction: state.jurisdiction,
        urgency: state.urgency,
        needs: [...state.needs],
        circumstances,
        housing,
        context_reviewed: true,
      }),
    });
    renderResults(await response.json());
  } catch (error) {
    showToast(`Could not build the plan: ${error.message}`);
  } finally {
    button.disabled = false;
    button.innerHTML = prior;
  }
}

function handoffText() {
  if (!state.navigation) return "";
  const handoff = state.navigation.handoff;
  return [
    `LAST-MILE HANDOFF ${handoff.reference}`,
    `Location: ${handoff.summary.location_shared}`,
    `Urgency: ${handoff.summary.urgency}`,
    `Needs: ${handoff.summary.needs.join(", ") || "not specified"}`,
    `Context: ${handoff.summary.circumstances.join(", ") || "not specified"}`,
    `Programs to ask about: ${handoff.summary.top_programs.join(", ") || "general review"}`,
    "No SSN, bank information, or documents are included.",
  ].join("\n");
}

function renderRawAlert(alert) {
  const properties = alert.properties;
  state.alert = alert;
  $("#raw-alert").innerHTML = `<b>HEADLINE</b>\n${escapeHtml(properties.headline)}\n\n<b>DESCRIPTION</b>\n${escapeHtml(properties.description)}\n\n<b>INSTRUCTION</b>\n${escapeHtml(properties.instruction || "[No instruction supplied]")}\n\n<b>AREA</b>\n${escapeHtml(properties.areaDesc)}`;
}

function renderChecks(segments) {
  const labels = {
    entity_integrity: ["Entity integrity", "Every locked fact appears exactly once"],
    semantic_fidelity: ["Meaning preserved", "Agreement stays above the safety threshold"],
    instruction_coverage: ["Actions covered", "Every source instruction maps to output"],
    grounding: ["No added claims", "Output asserts only what the source supports"],
  };
  $("#check-grid").innerHTML = Object.entries(labels).map(([key, [title, description]]) => {
    const failures = segments.filter((segment) => !segment.verification.checks[key].passed).length;
    return `<div class="check-card ${failures ? "fail" : ""}"><span class="check-icon">${failures ? "!" : "✓"}</span><h3>${title}</h3><p>${failures ? `${failures} segment${failures === 1 ? "" : "s"} refused` : description}</p></div>`;
  }).join("");
}

async function runTransform() {
  const output = $("#transform-output");
  output.className = "transform-output loading-block";
  output.textContent = "Locking critical entities, transforming, and verifying…";
  $("#run-transform").disabled = true;
  try {
    const response = await api("/api/transform", {
      method: "POST",
      body: JSON.stringify({
        language: $("#alert-language").value,
        grade: Number($("#alert-grade").value),
        simulate_failure: $("#simulate-failure").checked,
      }),
    });
    const result = await response.json();
    state.transform = result;
    state.alertPacket = result.protocol_packet;
    renderRawAlert(result.source_alert);
    output.className = "transform-output";
    output.innerHTML = result.segments.map((segment) => `
      <article class="segment ${segment.status === "verbatim_abstained" ? "abstained" : ""}">
        <div class="segment-top"><span class="segment-label">${segment.status === "verbatim_abstained" ? "Original English shown · translation withheld" : `✓ ${escapeHtml(segment.section)} verified`}</span><span class="segment-label">${segment.source_offset.start}–${segment.source_offset.end}</span></div>
        <p>${escapeHtml(segment.output)}</p>
        ${segment.status === "verbatim_abstained" ? `<p><strong>Reason:</strong> ${escapeHtml(segment.reason)}. Ask a 211 interpreter to read this source text.</p>` : ""}
        <details><summary>Inspect evidence</summary><pre>${escapeHtml(JSON.stringify({ entities: segment.entities, checks: segment.verification.checks, provider: segment.provider }, null, 2))}</pre></details>
      </article>`).join("");
    renderChecks(result.segments);
    $("#trust-boundary").textContent = result.manifest.trust_boundary;
    $("#source-hash").textContent = result.manifest.source.sha256;
    $("#play-audio").disabled = false;
    const alertPacket = result.protocol_packet;
    $("#alert-channel-strip").innerHTML = `<p><strong>${escapeHtml(alertPacket.protocol)}</strong> compiled this verified alert into every surviving channel · ${escapeHtml(alertPacket.proof.proof_id)}</p><div class="alert-channel-buttons">${["web", "sms", "voice", "offline"].map((channel, index) => `<button type="button" data-alert-channel="${channel}" class="${index === 0 ? "active" : ""}">${channel.toUpperCase()}</button>`).join("")}</div><div id="alert-channel-preview" class="alert-channel-preview">${escapeHtml(JSON.stringify(alertPacket.channels.web, null, 2))}</div>`;
    $("#verify-result").innerHTML = "";
  } catch (error) {
    output.textContent = `Transformation unavailable: ${error.message}`;
    showToast("The safe fallback kept the source visible.");
  } finally {
    $("#run-transform").disabled = false;
  }
}

async function verifyManifest() {
  if (!state.transform) return;
  const rendered = state.transform.segments.map((segment) => segment.output).join("\n");
  try {
    const response = await api("/api/verify", {
      method: "POST",
      body: JSON.stringify({ manifest: state.transform.manifest, rendered_text: rendered }),
    });
    const result = await response.json();
    $("#verify-result").innerHTML = `<div class="verify-badge ${result.valid ? "" : "fail"}">${result.valid ? "✓ Manifest signature and rendered content match." : "! Verification failed: the manifest or rendered content changed."}</div>`;
  } catch (error) {
    showToast(error.message);
  }
}

async function playAudio() {
  if (!state.transform) return;
  const text = state.transform.segments.map((segment) => segment.output).join(" ");
  const button = $("#play-audio");
  button.disabled = true;
  button.innerHTML = "Preparing…";
  try {
    const response = await fetch("/api/speech", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language: state.transform.language }),
    });
    if (response.ok) {
      const audio = new Audio(URL.createObjectURL(await response.blob()));
      await audio.play();
      showToast("Playing with Azure AI Speech");
    } else if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = { en: "en-US", es: "es-US", vi: "vi-VN", ko: "ko-KR", fa: "fa-IR" }[state.transform.language] || "en-US";
      window.speechSynthesis.speak(utterance);
      showToast("Azure Speech unavailable—using this device’s offline voice");
    } else throw new Error("No speech service is available");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = "<span>▶</span> Listen";
  }
}

async function checkFraud(event) {
  event.preventDefault();
  const text = $("#fraud-text").value.trim();
  if (!text) return showToast("Paste a message or link first.");
  const target = $("#fraud-result");
  target.className = "fraud-result empty-state";
  target.innerHTML = "<p>Checking red flags and official domains…</p>";
  try {
    const response = await api("/api/fraud-check", { method: "POST", body: JSON.stringify({ text }) });
    const result = await response.json();
    const low = result.risk === "no_obvious_red_flags";
    target.className = "fraud-result";
    target.innerHTML = `
      <div class="risk-banner ${low ? "safeish" : ""}"><p>RESULT</p><h2>${low ? "No obvious red flags found" : result.risk === "high" ? "Multiple red flags found" : "Use caution"}</h2><p>This does not prove the message is authentic.</p></div>
      ${result.findings.length ? `<ul class="finding-list">${result.findings.map((finding) => `<li>${escapeHtml(finding)}</li>`).join("")}</ul>` : "<p>No unusual-payment, pressure, sensitive-data, or unofficial-link pattern was detected by this limited check.</p>"}
      <p class="notice">${escapeHtml(result.notice)}<br /><br />${escapeHtml(result.report)}</p>`;
  } catch (error) {
    target.innerHTML = `<p>Check unavailable: ${escapeHtml(error.message)}</p>`;
  }
}

function adaptContextQuestions() {
  const mappings = {
    displaced: ["shelter", "housing", "home_repair"],
    renter: ["housing", "home_repair", "legal"],
    homeowner: ["housing", "home_repair"],
    no_id: ["shelter", "housing", "home_repair", "documents", "food", "money", "medical"],
    limited_english: ["shelter", "housing", "food", "money", "medical", "legal", "documents"],
    accessibility: ["shelter", "transportation", "medical"],
    lost_work: ["job", "money"],
    underinsured: ["home_repair", "housing", "money"],
    no_device: ["shelter", "housing", "food", "documents", "transportation"],
  };
  const needs = state.needs;
  $$("#context-grid label").forEach((label) => {
    const value = $("input", label).value;
    const relevant = (mappings[value] || []).some((need) => needs.has(need));
    label.hidden = !relevant;
    if (!relevant) $("input", label).checked = false;
  });
}

async function handleNext(button) {
  const destination = Number(button.dataset.next);
  if (destination === 2) {
    if (!$("#location").reportValidity()) return;
    try {
      const response = await api("/api/intake/next", {
        method: "POST",
        body: JSON.stringify({ location: $("#location").value, jurisdiction: state.jurisdiction, needs: [] }),
      });
      const result = await response.json();
      if (result.question?.id === "jurisdiction" && !state.jurisdiction) {
        $("#county-choices").innerHTML = result.question.choices.map((county) => `<button type="button" data-county="${escapeHtml(county)}">${escapeHtml(county)}</button>`).join("");
        $("#county-clarifier").hidden = false;
        showToast("One answer is needed because this ZIP crosses a county boundary.");
        return;
      }
    } catch (error) {
      showToast(`Location check used the local fallback: ${error.message}`);
    }
  }
  if (destination === 3) {
    if (!state.needs.size) return showToast("Choose at least one need so we can keep the plan focused.");
    adaptContextQuestions();
  }
  setStep(destination);
}

function setLowData(enabled, reason = "Manual low-data mode") {
  document.body.classList.toggle("low-data", enabled);
  const button = $("#low-data");
  button.setAttribute("aria-pressed", String(enabled));
  button.textContent = enabled ? "Low data: on" : "Low data";
  const banner = $("#connection-banner");
  banner.hidden = !enabled;
  banner.textContent = enabled ? `${reason}. Essential facts, actions, phone numbers, and proof remain available.` : "";
}

function updateConnectivity() {
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const unstable = !navigator.onLine || connection?.effectiveType === "2g" || connection?.effectiveType === "slow-2g";
  if (unstable) setLowData(true, navigator.onLine ? "Connection is unstable—switched to low-data mode" : "Offline—using the verified cached shell and last packet");
}

const innovations = [
  ["Need-first triage", "Starts with today’s need, then maps official programs—no agency knowledge required."],
  ["Confidence ladder", "Separates strong, possible, and worth-checking matches instead of pretending certainty."],
  ["Document escape hatch", "Shows agency-specific alternatives when identity or records were lost."],
  ["Privacy receipt", "Lists exactly what the match used, what was never requested, and that nothing was stored."],
  ["Human handoff packet", "Creates a short non-sensitive case summary and reference code so people do not repeat their story."],
  ["Segment-level refusal", "Withholds only the unsafe translation segment while preserving the rest of the message."],
  ["Provenance passport", "Signs the source hash, transformation chain, and segment outcomes for independent verification."],
  ["Fraud shield", "Checks pressure, unusual payments, sensitive-data requests, and known official domains."],
  ["Offline pocket plan", "Caches the app shell and creates a printable plan for unreliable connectivity or a shared device."],
  ["Grounded voice access", "Reads only verified text aloud through Azure AI Speech, with an on-device fallback."],
];

function init() {
  $$("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $$('[data-view-link]').forEach((link) => link.addEventListener("click", (event) => { event.preventDefault(); showView(link.dataset.viewLink); }));
  $$("[data-next]").forEach((button) => button.addEventListener("click", () => handleNext(button)));
  $$("[data-back]").forEach((button) => button.addEventListener("click", () => setStep(Number(button.dataset.back))));
  $$('[data-radio="urgency"]').forEach((button) => button.addEventListener("click", () => {
    $$('[data-radio="urgency"]').forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.urgency = button.dataset.value;
  }));
  $$(".need-chip").forEach((button) => button.addEventListener("click", () => {
    const value = button.dataset.need;
    if (state.needs.has(value)) state.needs.delete(value); else state.needs.add(value);
    button.classList.toggle("selected", state.needs.has(value));
    button.setAttribute("aria-pressed", String(state.needs.has(value)));
  }));
  $("#navigator-form").addEventListener("submit", submitNavigator);
  $("#location").addEventListener("input", () => {
    state.jurisdiction = null;
    $("#county-clarifier").hidden = true;
  });
  $("#county-choices").addEventListener("click", (event) => {
    const button = event.target.closest("[data-county]");
    if (!button) return;
    state.jurisdiction = button.dataset.county;
    $$("#county-choices button").forEach((item) => item.classList.toggle("selected", item === button));
    showToast(`${state.jurisdiction} selected. No more location detail is needed.`);
    window.setTimeout(() => setStep(2), 250);
  });
  $("#recommendation-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-details]");
    if (!button) return;
    const card = button.closest(".recommendation-card");
    card.classList.toggle("open");
    button.textContent = card.classList.contains("open") ? "Hide details −" : "What you’ll need +";
  });
  $("#print-plan").addEventListener("click", () => window.print());
  $("#copy-handoff").addEventListener("click", async () => { await navigator.clipboard.writeText(handoffText()); showToast("Handoff summary copied—no sensitive data included."); });
  $("#protocol-panel").addEventListener("click", async (event) => {
    const channelButton = event.target.closest("[data-packet-channel]");
    if (channelButton && state.packet) {
      state.packetChannel = channelButton.dataset.packetChannel;
      $$("[data-packet-channel]").forEach((item) => item.classList.toggle("active", item === channelButton));
      $("#channel-preview").textContent = channelText(state.packet, state.packetChannel);
      if (state.packetChannel === "voice" && "speechSynthesis" in window) showToast("Voice preview is ready; the same locked facts are preserved.");
    }
    if (event.target.closest("[data-copy-code]") && state.packet) {
      await navigator.clipboard.writeText(state.packet.continuity.resume_command);
      showToast("Anonymous recovery command copied.");
    }
    if (event.target.closest("[data-verify-packet]") && state.packet) {
      const response = await api("/api/packet/verify", { method: "POST", body: JSON.stringify({ packet: state.packet }) });
      const result = await response.json();
      showToast(result.valid ? "Packet signature, channels, and locked facts verify." : "Packet verification failed.");
    }
    if (event.target.closest("[data-send-sms]") && state.packet) {
      const phoneInput = $("#sms-number");
      const consent = $("#sms-consent").checked;
      try {
        const response = await api("/api/sms/send", {
          method: "POST",
          body: JSON.stringify({
            continuity_code: state.packet.continuity.code,
            phone_number: phoneInput.value.trim(),
            consent,
          }),
        });
        const result = await response.json();
        phoneInput.value = "";
        $("#sms-consent").checked = false;
        showToast(result.successful ? "Verified SMS accepted by Azure." : "Azure could not accept the SMS.");
      } catch (error) {
        showToast(error.message);
      }
    }
  });
  $("#run-transform").addEventListener("click", runTransform);
  $("#verify-manifest").addEventListener("click", verifyManifest);
  $("#play-audio").addEventListener("click", playAudio);
  $("#alert-channel-strip").addEventListener("click", (event) => {
    const button = event.target.closest("[data-alert-channel]");
    if (!button || !state.alertPacket) return;
    $$("[data-alert-channel]").forEach((item) => item.classList.toggle("active", item === button));
    $("#alert-channel-preview").textContent = JSON.stringify(state.alertPacket.channels[button.dataset.alertChannel], null, 2);
  });
  $("#download-manifest").addEventListener("click", () => {
    if (!state.transform) return;
    const blob = new Blob([JSON.stringify(state.transform.manifest, null, 2)], { type: "application/json" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob); anchor.download = "last-mile-manifest.json"; anchor.click();
    URL.revokeObjectURL(anchor.href);
  });
  $("#fraud-form").addEventListener("submit", checkFraud);
  $$('[data-fraud-example]').forEach((button) => button.addEventListener("click", () => {
    $("#fraud-text").value = button.dataset.fraudExample === "scam"
      ? "FINAL WARNING: Pay a $75 processing fee by gift card now to guarantee your FEMA approval. Send your SSN and bank password at https://fema-help-fast.example.com"
      : "You can review disaster assistance at https://www.disasterassistance.gov/ and apply only through the official site.";
  }));
  $("#text-size").addEventListener("click", () => document.body.classList.toggle("large-text"));
  $("#low-data").addEventListener("click", () => setLowData(!document.body.classList.contains("low-data")));
  $("#use-location").addEventListener("click", () => {
    if (!navigator.geolocation) return showToast("Location is not available on this device.");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => { $("#location").value = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`; showToast("Location added for this one-time check."); },
      () => showToast("Location permission was not granted. A city or ZIP works too."),
      { enableHighAccuracy: false, timeout: 6000 }
    );
  });
  $$('[data-modal]').forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.modal}`).showModal()));
  $$("dialog .dialog-close").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  $("#innovation-grid").innerHTML = innovations.map(([title, description], index) => `<article class="innovation-card"><span>${String(index + 1).padStart(2, "0")}</span><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(description)}</p></div><span class="implemented-badge">Implemented</span></article>`).join("");

  api("/api/status").then((response) => response.json()).then((status) => { state.providers = status.providers || {}; }).catch(() => {});
  api("/api/alerts").then((response) => response.json()).then((alerts) => renderRawAlert(alerts.features[0])).catch(() => {});
  window.addEventListener("online", updateConnectivity);
  window.addEventListener("offline", updateConnectivity);
  if (navigator.connection) navigator.connection.addEventListener("change", updateConnectivity);
  updateConnectivity();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/assets/sw.js").catch(() => {});
}

document.addEventListener("DOMContentLoaded", init);
