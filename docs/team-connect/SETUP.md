# Technical source and asset setup

The public code snapshot is `349b3664c4165f3522ba8a92e9a6d830581e0d68`, on `publish/team-connect-verified-2026-10-29`. This successor is a local proposal; its current-synthetic and reusable financial features are not in that published snapshot. Clone the verified public branch only when you intend that older version. Use the final successor commit only after its exact publication is approved and its remote SHA verified.

```sh
git clone --branch publish/team-connect-verified-2026-10-29 https://github.com/Sploosh4/greenspark-hackathon.git
cd greenspark-hackathon
git rev-parse HEAD
```

## Assets and exact versions

Git includes implementation, contracts, lightweight public reference JSON, licences and selected authored test fixtures. It excludes full model bundles, wheels, replay outputs, current-input/integration fixtures, raw upload packs and large history layers. [ASSET-MANIFEST.json](ASSET-MANIFEST.json) records exact groups. The selected local `FINAL_DEMO_PACKAGE.zip` has SHA256 `d67990f338af7eb205b6f6d080c8e663931742e47068221fcfaa2a78a5deefaf`; both ready-to-upload folders were hash-checked. There is no approved public asset-download URL. Private Library/Drive/local paths must not be presented as public downloads.

| Asset group | Purpose and boundary |
|---|---|
| `q1-inputs`, `q1-replay` | Original historical input pack and sealed 37-customer JSON/CSV; unchanged generation identity. Original replay has local-path metadata needing review before redistribution. |
| `q1-current-upload-20261029` | Twelve business files, 120 customers; scenario 29 October–4 November 2026. Staleness rules remain active on later review days. |
| `q1-current-model-bundle` | Exact 17-file frozen bundle including its original 16-file manifest; required for current inference, not historical JSON serving. No listed binary or training-prior file is in Git. |
| `q1-current-wheels` | Eight pinned official CPython 3.12 Linux x86_64 wheels. [URLs and checksums](Q1-CURRENT-WHEELS.json) identify upstream public artifacts; no download/install ran here. |
| `q1-current-tests` | Five owner integration fixtures, external to Git pending a reviewed redistribution/metadata decision. These are app fixtures, not reserved scorer answers. |
| `q3-history` | 96 PNG/gzip files for 48 history layers; matching `metadata.json` is already in source. |
| `q3-business-50000`, `q3-financial-50000` | Older accepted statewide cohort at 30 June 2025; active native data remains this dated snapshot. |
| `q3-current-financial-50000` | Fresh eight-file selected package, manifest `ff77c62ef33f9c68eb71d8edbbcadb00008a954c94e6d9534d03329bf3f51338`, snapshot 30 September 2026, 11 populated areas; not activated in native state. |

Obtain approved assets from the owner, safely unpack into new directories and verify only the intended group:

```sh
python3 scripts/team-connect/verify-assets.py --asset q1-inputs --root /absolute/path/to/historical-inputs
python3 scripts/team-connect/verify-assets.py --asset q1-replay --root /absolute/path/to/replay
python3 scripts/team-connect/verify-assets.py --asset q1-current-upload-20261029 --root /absolute/path/to/Q1
python3 scripts/team-connect/verify-assets.py --asset q1-current-model-bundle --root /absolute/path/to/frozen_v3
python3 scripts/team-connect/verify-assets.py --asset q1-current-wheels --root /absolute/path/to/wheels
python3 scripts/team-connect/verify-assets.py --asset q3-current-financial-50000 --root /absolute/path/to/Q3
python3 scripts/team-connect/verify-assets.py --asset q3-history --root apps/q3-community-planning/data/history
```

The verifier reads only manifest-listed regular files, rejects symlinks/escaping paths and prints no contents. It downloads, extracts, activates and provisions nothing. A checksum is integrity evidence, not a signature or redistribution permission.

## Reviewed public asset strategy: decision still pending

Propose a separate immutable release delivery, tied to the exact source commit, with distinct historical, current synthetic, history and model artifacts plus byte counts, SHA256, licences, dates and limitations. This is a proposal, not approval to create a GitHub release, upload files or broaden sharing. Keep reserved scorer material, private account/state files, personal paths and credentials out. Do not copy the generator workspace wholesale.

The owner must inspect rights and content of each proposed artifact before publication. Original replay/integration metadata may need redaction and resealing with new IDs/export hashes and regression review. The frozen model's `FILE_MANIFEST.json` is pinned as `c4a09dadf6544992d0c931a11e86e662aa3d2106d513c2165701c08c72e72db7`; changing any manifest-bound file requires a separately reviewed compatible release/pin and acceptance. Do not silently edit a bundle while claiming the old identity. The model delivery's training-prior/selection metadata needs the same exclusion review; its presence in a trusted runtime bundle does not automatically permit public distribution. Official wheels can stay at their immutable upstream URLs rather than being mirrored.

After exact artifact approval, publish only the reviewed payload, verify availability from outside the owner's account, then replace null download fields with the verified public URLs. Until then, this source is not a complete self-service public demo delivery.

## Local application modes

Week Ahead historical preview uses the generic launcher with `Q1_SOURCE_DIR`, an approved replay JSON and `--replay-mode simulated_historical_replay`. Explicit preview requires `TEAM_CONNECT_UNAUTHENTICATED_DEMO=1` and loopback only; it must not be exposed. Direct `serve.py` does not select the replay automatically.

Current synthetic uploads require the authenticated generic launcher. Remove the preview opt-in, supply `--auth-store` through a separately approved read-only identity path, and add `--current-uploads --current-python /absolute/path/to/approved/python3.12`. Place the exact approved frozen bundle under `prototype/vendor/frozen_v3` in the private runtime copy, not Git. Its dependency guard rejects an incompatible runtime before deserialisation. Do not copy ongoing laptop accounts/passwords. Use only a free canonical 8891 port and an isolated approved state path; do not start over an existing owner.

The twelve current business files are staged asynchronously; validation/calculation must finish before deliberate replacement. The default historical replay remains available. Freshness requires seven complete reported usage days ending one or two days before review, plus suitable fresh modelled weather. Weather scheduling cannot refresh stale business records. Source availability, upload receipt, inference time, forecast retrieval/load and unknown provider issuance remain separately labelled.

Season Ahead's direct `python -B run.py` entry point is a loopback preview at 127.0.0.1:8797. The local boundary needs no MapTiler key. Authenticated operation uses the separate launcher/identity overlay. Business intake takes `customers.csv` and `consumption_daily.csv.gz`. Financial intake takes those two, `manifest.json` and the five support/payment gzip files. Valid fresh input declares `q3-synthetic-financial-v1` and passes actual row/join/lifecycle/amount/resource validation; user-supplied hashes alone do not grant acceptance. Stage, review and explicitly replace business first, then its matching financial package. No source promotion activates data automatically.

## Container recipes and checks

The ordinary [packaging guide](../../packaging/team-connect/README.md) stages source-only contexts. Historical mode uses base/authenticated/replay overlays; optional history uses `compose.history.yaml` with the verified directory containing `metadata.json` and 96 files. The layers and replay are read-only binds.

`Dockerfile.q1-current`, `requirements-q1-current.txt`, `.dockerignore.current` and `compose.q1-current-isolated.yaml` retain the accepted owner's current-image recipe with portable context/volume names and an external replay bind. It uses Python 3.12.16 and hashed offline wheels, UID10001, 1 CPU/1 GiB, read-only root, no host ports, no network and no scheduler. The generic stager includes the inference tool text, but does **not** assemble the external model/wheel bundle. Before a current build, an approved operator must assemble and hash-review `build/q1-current-candidate`: selected app/runtime/font source, the exact frozen bundle at `app/prototype/vendor/frozen_v3`, the eight wheels at `wheels/`, current requirements and the current Dockerfile/ignore file. No current context, image or deployment was built by this proposal. External identity/state volumes must already exist; the recipe provisions none.

Run the app and packaging regression commands recorded in [VALIDATION.md](VALIDATION.md), with their exact external fixture prerequisites. Socket opt-ins remain separate. Existing Host/Origin/HTTP-cookie checks are for loopback; public HTTPS requires the separate reviewed origin/Secure-cookie implementation and deployment acceptance. Operational user guides remain paused pending final workflow review; this file is technical setup only.
