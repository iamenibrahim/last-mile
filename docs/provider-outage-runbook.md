# Provider outage drill

The automated drill is `tests/test_provider_resilience.py`.

It forces Microsoft Foundry and Azure Translator to time out before any output
is returned. The required result is a complete response from the curated or
deterministic local engine with `fallback_reason=TimeoutError`. Content Safety
remains fail-closed: if its final guard cannot run, a transformed segment is not
published.

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_provider_resilience.py -q
```

For a production exercise, use a staging slot and remove one provider key from
that slot only. Never run a deliberate outage against the competition demo or a
citizen-facing production instance.
