# Team Connect code publication

This working branch imports Q1 build `291739b9a9cf2484`, the reviewed Q1 Sign out patch `d83e19778fc51ebd`, and Season Ahead source `209bce1ae503`. The existing repository demo is preserved. Application source and tests were selected from hash-verified frozen owner snapshots rather than the live working trees.

The import includes app code, upload contracts, tests, necessary browser assets, container recipes, licences and small public reference or labelled synthetic fixture JSON. It excludes credentials, private account stores, session secrets, runtime state, private reports, original customer packs, large climate layers, model binaries, reserved evaluation inputs/answers and personal files.

The in-progress Q1 observed-weather, ML and v3 replay work is excluded. The reviewed read-only identity adapter and explicit authenticated-container launchers are included. Native service wrappers, account provisioning, account stores and all credentials are excluded. Direct app entry points retain their preview defaults; authenticated container mode requires a separate overlay and pre-provisioned private volumes. This is not a production-security or full project-acceptance claim.

Portability changes replace the original laptop paths with `Q1_SOURCE_DIR`, `Q1_SHARED_WEATHER_CACHE`, the user's home for the standard CDS credential location, and app-relative provider/reference paths. The Q1 test fixture helper now reads the configured pack's schema manifest. Container staging uses the app directories in this repository. Preview startup requires explicit opt-in; the authentication overlay clears that mode and mounts separate read-only identities. The frozen prediction arithmetic and climate decoder are unchanged.

The Sign out patch matched all expected base hashes before import. It adds session termination, protected-state cleanup and delayed-response/BFCache guards. The identity adapter matches the independently reviewed source. Selected runtime packaging files were copied only after their before/after hashes matched. Tests of this local package are separate from the runtime owner's ongoing integration and image tests.

Q1's current live impact estimates remain unavailable when recent usage coverage is missing. Historical replay and synthetic fixtures do not validate model accuracy or official BoM heat categories. Season Ahead's bundled initial aggregate pack is distinct from the live 50,000-account cohort. Large history layers must be provided separately. These limits remain beside the app instructions.

Source attribution is retained in the app licences, Q1 EHF reuse notes, Season Ahead data provenance, and MapLibre licence. The synthetic fixtures are authored test data under the relevant app/repository licence. Public climate and census data retain their upstream terms. [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json) records imported source hashes and any publication changes without private laptop paths.

The publication changes no repository permissions, merges no branch, installs no service, enables no public deployment and sends no submission or email.
