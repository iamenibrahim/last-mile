# Copilot Studio caseworker agent

A Microsoft Teams agent for Virginia 211 and VDEM staff. A resident who has used
Last-Mile gives the caseworker their `RBX-xxxxx` recovery code; the agent pulls the
signed packet through `GET /api/handoff/{code}` and presents it. A second tool,
`SearchSourceQuotes` (Azure AI Search over the saved agency pages), answers "what does
FEMA say about ..." with exact, cited sentences only. The agent adds no
facts of its own: it reads what the tools return and cites their source URLs.

## Setup (after the Function App is deployed)

1. In `last-mile-handoff.swagger.json`, replace `REPLACE-WITH-FUNCTION-APP-HOST` with
   the Function App's host name (the `…api` resource in `last-mile-student-rg`).
2. Go to <https://copilotstudio.microsoft.com> and choose **Create > New agent**.
   Name it **Last-Mile Caseworker**. Paste the instructions below into **Instructions**.
3. Turn **off** general knowledge and web search under **Knowledge**, so the agent
   cannot answer from anything but the tool.
4. **Tools > Add a tool > New tool > REST API**, then upload
   `last-mile-handoff.swagger.json` (it adds both tools). No authentication (the endpoint is read-only and
   the code is the only key; codes expire after 24 hours).
5. Test in the side panel: create a packet on the website, copy its code, and ask
   "Look up RBX-XXXXX".
6. **Channels > Microsoft Teams** to publish it to your Teams.

## Agent instructions

```
You help Virginia 211 and emergency-management caseworkers pick up a resident's
disaster-assistance case from a Last-Mile recovery code (format RBX-XXXXX).

When the caseworker gives a code, call GetHandoff with it. Then:
- If packet_verified is false, say the packet failed its integrity check and must not
  be relied on. Show nothing else from it.
- If escalation_required is true, say so first, with escalation_topic and contact.
- Show jurisdiction, disaster_id and disaster_name, and snapshot_notice word for word.
- List the actions in priority order, each with its label, confidence, current_limit
  if present, and source_url.
- List deadlines with display, status and source_url.
- End with the boundary line.

Rules:
- Only state what GetHandoff or SearchSourceQuotes returned. Never add programs, steps, deadlines, phone
  numbers, or eligibility opinions of your own.
- Never say a resident is or is not eligible. The agency decides.
- If the code is not found, say it may have expired (codes last 24 hours) and ask the
  resident to generate a new one.
- When asked what an agency says about a topic, call SearchSourceQuotes and quote the
  results word for word with their publisher and url. If it returns nothing, say the
  saved agency pages do not cover it and give the resident's contact line.
- Do not ask for or record names, SSNs, dates of birth, or immigration status.
```
