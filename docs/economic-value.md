# Economic-value and operating-cost model

No dollar-savings claim is made without partner data. The checked-in calculator makes the assumptions inspectable:

```powershell
python scripts/economic_value.py --calls 10000 --deflection 0.10 --minutes-saved 4 --hourly-cost 35
```

That command is an illustrative scenario, not evidence. Replace the inputs with a contact center's monthly disaster-call volume, measured deflection or handle-time change from a pilot, and loaded labor cost. Report the result as recovered service capacity unless the agency confirms that it produces cash savings.

For a defensible study, record baseline and pilot cohorts for average handle time, abandonment rate, first-contact resolution, transfers, and time-to-authoritative-application. Keep the same incident type and measurement window where possible.

Azure operating cost must be reported separately from economic value. Export actual Cost Management data after the live pilot and group it into Functions/Storage, Foundry inference, Translator, Speech, Content Safety, Maps, Search, Key Vault, monitoring, and Communication Services. The student deployment uses scale-to-zero compute and existing Function storage; SMS/voice charges remain zero until a sender is obtained and enabled. Do not substitute public list prices for the subscription's actual invoice.
