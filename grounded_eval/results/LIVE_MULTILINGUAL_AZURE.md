# Live Azure multilingual evaluation

Generated: 2026-09-24T03:50:47Z

> One deployed alert per language. This is a provider smoke evaluation, not a native-speaker quality study.

| language | successful | withheld | withholding | locked entities | entity failures | provider errors | latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| es | 3/7 | 4 | 57.1% | 11 | 0 | 0 | 6838.7 ms |
| ar | 2/7 | 5 | 71.4% | 11 | 0 | 0 | 3432.4 ms |
| prs | 3/7 | 4 | 57.1% | 11 | 0 | 0 | 3494.6 ms |
| tl | 1/7 | 6 | 85.7% | 11 | 0 | 0 | 3003.1 ms |

Provider errors count explicit cloud fallbacks reported by the response. Withholding is expected fail-closed behavior when a transformed segment cannot be verified.
