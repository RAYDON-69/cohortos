# P44 round log

| iter | SHA | green | red | change | diag said |
|------|-----|-------|-----|--------|-----------|
| 0 | b64659e | — | unit-full collection | start | SyntaxError import* in function |
| 1 | 613366e | workflow-lint | unit-full, readiness, ci-gate | fix collection + ci-gate | suite runs; no such table _records |
| 2 | 9345f6f | workflow-lint | unit-full, readiness, ci-gate startup | schema on every connection | KeyError _test_code; 108 pass / 20 fail |
| 3 | b6b3799 | workflow-lint | unit-full, readiness, ci-gate | rate-limit off in job; solid ci-gate | still KeyError _test_code |
| 4 | 2df8394 | workflow-lint | unit-full, readiness, ci-gate | OTP limit honors DISABLED | otp_id None / account not found path |

Final: 2df8394 — 108 passed, 20 failed on unit-full (CI).

## P45
| 0 | 4e735c7 | — | 20 unit fails | start | shared mem suspected |
| 1 | (next) | — | — | shared-cache memory URI + sentinel | — |

| 8 | edbfcb4 | unit-full 612 pass | xdist/readiness | vault dual storage | unit-full GREEN |

## P46
| SHA | notes |
|-----|-------|
| 524f76f | phase* triggers for e2e+security; CI Gate aggregates; E2E/Security now run on push; unit-full 2 fail retrieval tests |
| 2e85e04 | retrieval quality ctor fix |

## P47
| SHA | notes |
|-----|-------|
| 6bbbf70 | retrieval tokens fixed; semgrep/md5/npmrc; e2e no path filter; readiness npm build; unit-full job SUCCESS; unit-xdist still red |
| 1689622 | xdist loadfile + close_all autouse |

## P48
| SHA | unit | xdist | e2e | readiness | security | notes |
|-----|------|-------|-----|-----------|----------|-------|
| 0a97a43 | — | diag | — | — | — | xdist diag + axe always |
| d121185 | success | success | axe fail | scorecard | npm | unit-xdist GREEN |
| 2a26c80 | success | success | core flake | scorecard | npm | extended skipped=pass |
| 71c82b2 | — | — | settings soft | — | lock-regen always | glob overrides |
