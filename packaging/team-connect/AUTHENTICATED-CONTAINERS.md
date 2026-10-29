# Explicit authenticated container mode

`compose.authenticated.yaml` selects authenticated serving for Q1 and Season Ahead. It removes the preview environment and passes `--auth-store /identity/auth.sqlite3` to each launcher. A missing store or a conflicting preview flag fails before serving. Direct app entry points and the base Compose recipe retain their separate preview behaviour.

Each app requires its own already-provisioned external identity volume. Mounts are read-only at `/identity`; writable app state remains in separate volumes. The identity directory must be owner-only `0700` and its database `0600`, owned by UID `10001` for Q1 or `10002` for Season Ahead. No account is created by these recipes. Native laptop stores must not be copied, re-owned or made less private to fit an image; a real-account cutover requires a separately approved mapping/provisioning and port/scheduler handoff.

The adapter expects SQLite `user_version=1`, one matching `instance_meta(instance)` row (`q1` or `q3`), and an `accounts` table with `account_id`, `username`, `role`, `salt`, `digest`, `enabled`, `credential_version` and `kdf`. Salt and digest lengths are 16 and 32 bytes; KDF metadata is `scrypt:N=131072,r=8,p=1,dklen=32`. Q1 supports officer/manager roles; Season Ahead admits managers. Lookups reload role, enabled state and credential version. Provisioning code and real databases are deliberately absent from this package.

Both launchers apply session-only, host-only cookies with HttpOnly and SameSite=Strict. Default idle and absolute limits are 1,800 and 28,800 seconds. Opaque random session tokens are retained only as hashes in process memory; restart invalidates sessions. No persistent session signing secret is required. These are local HTTP recipes; an HTTPS deployment and Secure-cookie policy require separate review.

After running `python -B stage.py`, configuration can be inspected without starting a container:

```bash
export Q1_SOURCE_DIR=/path/to/approved/synthetic/Q1/inputs
export Q1_IDENTITY_VOLUME=approved-q1-private-identity
export Q3_IDENTITY_VOLUME=approved-q3-private-identity
docker compose -f compose.yaml -f compose.authenticated.yaml config
```

The staged contexts are `build/q1` and `build/q3`. The authenticated overlay uses these same contexts and separate runtime identity mounts. `compose.authenticated-test.yaml` removes host ports for isolated testing. No command here installs services, provisions identities or performs a deployment. Do not start containers over occupied native ports.

This publication package passed temporary-identity launcher tests and Compose configuration checks. The read-only adapter matches the independently reviewed native identity code. The Q1 Sign out patch is present in the staged source. No final image build, real-account login or integrated running-container test was performed by this publication task; the runtime owner's earlier or ongoing tests retain their own source/version limits.
