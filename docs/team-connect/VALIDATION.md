# Publication validation

Checks run on the imported branch on 29 October 2026:

| Check | Result and scope |
|---|---|
| Q1 Python | 130 collected: 122 passed, 8 canonical-port HTTP tests skipped. The configured authorised synthetic input pack was read locally; the derived report is ignored and excluded. |
| Q1 JavaScript | All 7 test files passed. |
| Season Ahead Python | 157 passed. `test_history_archive.py` was excluded because its large matching external SILO layers are absent from this code publication. |
| Season Ahead JavaScript | All 14 test files passed, including native-history client tests using metadata. |
| Packaging | Staging completed and 9 tests passed. |
| Compose | YAML parsed; static checks passed for loopback ports, separate non-root users, read-only roots, dropped capabilities, input mount protections and required preview opt-in. |
| Source integrity | Imported files matched the frozen owner manifests before the documented portability and whitespace edits. Published hashes are recorded in `SOURCE-PROVENANCE.json`. |
| Publication boundary | Selected staged blobs were checked for excluded file types/paths, private laptop paths, common credential/token formats, private keys, credential-bearing URLs and long literal secret assignments. No matches were found. This is a scoped pattern and allowlist check, not proof that every possible secret format is detectable. |

No fresh Docker image build, container start, deployed service check, live password login, model accuracy benchmark or full managed security scan was run for this branch. The original repository has no tracked GitHub Actions workflow at the publication base. Remote commit verification and any remote check results belong to the separate publication receipt.
