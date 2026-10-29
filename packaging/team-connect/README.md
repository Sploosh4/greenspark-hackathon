# Local container recipes

These recipes package the reviewed Q1 and Season Ahead source without copying live state. They use pinned Python images, hashed PDF dependencies, non-root users, separate state volumes and loopback-only published ports.

Run `python -B stage.py` here to create ignored `build/q1` and `build/q3` contexts. Staging uses the app directories in this checkout and rejects symlinked source paths. Q1 also needs the reviewed DejaVu Sans font installed at `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, with SHA-256 `b4c632e3cdf9acc7f28758fb5a323c8524d7fc6660d46904d9b6cbe2809c419c`, plus its distro copyright file. The font binary is copied only into the generated context.

Set `Q1_SOURCE_DIR` to the authorised external synthetic input pack. Set `TEAM_CONNECT_UNAUTHENTICATED_DEMO=1` explicitly for an isolated synthetic preview. The base configuration defaults this flag to `0` and refuses to start a preview without opt-in. Build and start only when the two canonical host ports are free; do not start this example over an existing app instance.

For explicit authenticated serving, combine the base with `compose.authenticated.yaml` and supply two separately provisioned, read-only private identity volumes. The overlay removes preview mode. It creates no accounts and does not copy native stores. See [AUTHENTICATED-CONTAINERS.md](AUTHENTICATED-CONTAINERS.md) for prerequisites and the test overlay that removes host ports.

Run `python -B -m unittest discover -s tests -p 'test_*.py'` after staging. These tests use temporary identities and stubbed server creation without opening listeners; Compose checks only render configuration. A fresh image build was not executed for this branch. Runtime-owner container results apply to their recorded snapshots, not to a new build of this checkout. No deployment or container start is performed by staging or the tests.
