# Ten implemented innovations

1. **Canonical Disaster Action Packet.** Jurisdiction, declaration, deadline, needs, actions, source hashes, constraints, and escalation live in a channel-independent schema in `api/protocol.py`.
2. **Proof-Carrying Guidance.** Packet state and compiled channels are hashed and signed. Every channel carries the same proof ID and locked government facts; `/api/packet/verify` detects drift.
3. **Cross-channel continuity.** An anonymous 24-hour `RBX-xxxxx` code resumes county, disaster, broad need, non-sensitive constraint, generic escalation, and step state. The web UI now resumes the code directly. It excludes names, exact addresses, SSNs, bank data, documents, and sensitive handoff reasons.
4. **Connectivity-aware degradation.** Offline/slow-network detection switches the UI to a low-data mode. A citizen can explicitly save the signed minimal packet on the device, reopen it without a connection, and remove it before leaving a shared device.
5. **Minimum-necessary questioning.** `/api/intake/next` asks only when an answer changes guidance. ZIP `24370` triggers a county question; the packet records possible, asked, and skipped question groups.
6. **Resolution-ready human handoff.** Rules explicitly distinguish urgent, sensitive, ambiguous, and high-impact cases. The handoff includes county, disaster ID, broad needs, what remains unresolved, official contact paths, and a script the survivor can read aloud without persisting the sensitive reason.
7. **One protocol across the lifecycle.** NWS warning packets and FEMA recovery packets share provenance, locked facts, channel compilation, abstention, and delivery representations.
8. **Segment-level refusal.** Entity locking and four independent checks let one unsafe sentence fall back to exact source English without discarding the whole alert.
9. **Disaster Fraud Shield.** The app detects unusual payment requests, pressure language, sensitive-data requests, and non-allowlisted links, while never declaring a message safe.
10. **Verified language, voice, and offline access.** The language entry point routes to verified Spanish, Arabic, Dari, and Tagalog/Filipino output. Only post-verification text reaches Azure AI Speech or device speech; the exact packet also compiles to an explicitly saved, removable offline view.

## Rubric fit

- **Performance:** mechanism tests, corruption classes, visible refusal, channel hash verification, p50/p95 timing, and full-flow API tests.
- **Innovation:** a proof-carrying protocol, not a collection of disconnected bots and pages.
- **Economic and societal impact:** less repeated intake, better-prepared callers, fewer dead-end applications, and broader literacy/connectivity access. No time-savings percentage is claimed without measurement.
- **Feasibility:** public sources, no data agreement for the demo, no front-end build, narrow Azure interfaces, and deterministic fallbacks.
