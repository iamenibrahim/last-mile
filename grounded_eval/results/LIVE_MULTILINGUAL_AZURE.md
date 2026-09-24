# Live Azure multilingual evaluation

Generated: 2026-09-24T12:23:23Z

> One deployed alert per language. This is a provider smoke evaluation, not a native-speaker quality study.

| language | successful | withheld | withholding | locked entities | entity failures | provider errors | latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| es | 6/7 | 1 | 14.3% | 11 | 0 | 0 | 2003.5 ms |
| ar | 7/7 | 0 | 0.0% | 11 | 0 | 0 | 1581.2 ms |
| prs | 6/7 | 1 | 14.3% | 11 | 0 | 0 | 1705.3 ms |
| tl | 5/7 | 2 | 28.6% | 11 | 0 | 0 | 1729.9 ms |

Provider errors count explicit cloud fallbacks reported by the response. Withholding is expected fail-closed behavior when a transformed segment cannot be verified.
