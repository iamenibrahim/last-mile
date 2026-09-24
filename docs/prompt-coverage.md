# Challenge-prompt coverage

This is a claim-to-evidence map for the disaster-assistance navigator prompt. “Implemented” means the behavior exists in the submitted runtime; it does not mean an agency has approved it for production.

| Prompt requirement | Implemented behavior | Evidence / boundary |
|---|---|---|
| Discover assistance by location | City, ZIP, optional address, county disambiguation, declaration matching, alert geometry, and official application links | Geometry and deterministic rules—not an LLM—decide location applicability |
| Circumstances and immediate needs | Need-first intake plus optional broad constraints; irrelevant follow-up groups are skipped | No income amount, immigration status, SSN, bank details, FEMA registration number, or uploads |
| Whether someone may qualify | Confidence ladder, reviewed program gates, missing-information display, and an explicit agency-decision caveat | The system screens; it never issues an eligibility determination |
| Information and documents needed | Per-program checklists and lost-document alternatives | Official agency decides which alternatives it accepts |
| Where to apply | Official program links, DisasterAssistance.gov, Virginia 211, FEMA helpline, and FEMA Disaster Recovery Center Locator | Current hours, deadlines, and center availability must be reconfirmed on the official site |
| Better than a phone menu | Three-step adaptive intake, ranked plan, “why this fits,” printable handoff, and questions-skipped audit | Contact-center time reduction still requires a partner pilot |
| Authoritative government grounding | Reviewed FEMA/eCFR/SBA/SAMHSA records, OpenFEMA data, NWS CAP, exact quotes, hashes, citations, and signed packet state | Cached records are labeled; they never prove a program is currently open |
| Plain language | Microsoft Foundry explanations over supplied records and grade-targeted transformations | Foundry cannot choose eligibility or originate emergency actions |
| Different languages | Verified Spanish, Arabic, Dari, and Tagalog/Filipino path using Azure Translator, round-trip checks, segment abstention, and interpreter referral | Native-speaker review is still required; unsafe segments remain in English |
| Accessibility needs | Keyboard-native controls, skip link, semantic headings, text enlargement, high contrast, reduced-motion support, speech, 711, print, and human alternatives | Formal WCAG/Section 508 audit and testing with disabled users remain outstanding |
| Unreliable connectivity | Automatic low-data mode, cached PWA shell, print, and explicit offline save/open/remove for the signed minimal packet | Offline saving is opt-in and warns against shared-device use |
| Lost device or channel | Anonymous 24-hour `RBX-xxxxx` code can be resumed on the web and is compiled into SMS/voice commands | Real SMS/voice delivery remains disabled until an ACS sender is obtained |
| Urgent help | Persistent 911 boundary and danger-first result above benefit guidance | The system does not dispatch emergency services |
| Minimize sensitive data | Coarse location retention, privacy receipt, no request-body telemetry, expiring minimal packet, and exclusion of sensitive handoff reasons | Official application sites may request more after the citizen chooses to apply |
| Disaster fraud | Red-flag scanner, official-domain allowlist, FEMA/DOJ reporting path, and explicit “not proof of authenticity” warning | The scanner never labels a message safe |
| Human escalation | Explicit urgent, sensitive, ambiguous, high-impact, language, accessibility, lost-ID, and low-confidence routing | Copilot Studio connector is prepared but tenant publication is still required |

## Material external work still required

1. Obtain an Azure Communication Services phone number and complete real SMS and Call Automation delivery.
2. Publish the prepared Copilot Studio actions in an authorized tenant.
3. Conduct the five-person citizen/caseworker usability study and native-speaker review.
4. Complete an accessibility audit with keyboard, screen-reader, low-vision, cognitive-accessibility, and disabled-user testing.
5. Measure contact-center handle time, abandonment, transfer rate, and time-to-assistance with a real partner.
6. Run the Census B16004 coverage analysis and a longer sustained/load/disaster-recovery test.
7. Redeploy an agency-approved production instance in a suitable US region with formal security and data-governance review.
