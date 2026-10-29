# Publication validation

Checks run on the imported branch on 29 October 2026:

| Check | Result and scope |
|---|---|
| Q1 Python | 131 collected: 123 passed, 8 canonical-port HTTP tests skipped. The configured authorised synthetic input pack was read locally; the derived report is ignored and excluded. |
| Q1 JavaScript | All 8 test files passed, including Sign out, failure/retry, expiry, delayed responses, protected-state cleanup and BFCache handling. |
| Season Ahead Python | 157 passed. `test_history_archive.py` was excluded because its large matching external SILO layers are absent from this code publication. |
| Season Ahead JavaScript | All 14 test files passed, including native-history client tests using metadata. |
| Packaging | Restaging completed and 18 tests passed. Tests use temporary SQLite fixtures, actual identity/session classes and stubbed server creation without listening sockets. Missing identities, ambiguous modes and implicit previews fail before serving. |
| Compose | Base/authenticated and base/authenticated/test combinations rendered through `docker compose config`. Checks passed for mode separation, external read-only identity volumes, loopback or removed host ports, separate users, read-only roots, dropped capabilities and input mount protections. No image was built or container started. |
| Source integrity | Imported files matched the frozen owner manifests before the documented portability and whitespace edits. Published hashes are recorded in `SOURCE-PROVENANCE.json`. |
| Publication boundary | Selected staged blobs were checked for excluded file types/paths, private laptop paths, common credential/token formats, private keys, credential-bearing URLs and long literal secret assignments. No matches were found. This is a scoped pattern and allowlist check, not proof that every possible secret format is detectable. |

The Season Ahead results above are retained from its unchanged application source in the first local publication commit. The Q1 and packaging checks were rerun after the Sign out/authenticated-launcher update. No fresh Docker image build, container start, deployed service check, live password login, model accuracy benchmark or full managed security scan was run for this branch. Runtime-owner integration results apply to their own recorded snapshots. The original repository has no tracked GitHub Actions workflow at the publication base. No remote mutation or CI run was requested for this local package update.
