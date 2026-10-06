# Release 3.0.0

This document records the publication procedure for the experimental 3.0.0
prerelease and future maintenance. The workflow publishes versioned images;
GitHub Releases are created separately after verification. Keep the current
public installation usable until the replacement images are publicly available.
The `image` field instructs HA to pull `ghcr.io/spruben/d2ha-bridge:3.0.0`; HA
will not build a fallback if that image is missing or private.

## Repository rename and owner tasks

The existing repository was renamed to `d2ha-bridge`, retaining its repository ID and history. Never delete/recreate it. Verify the same repository ID, history and default branch when checking the rename. Keep the old GitHub name unused so redirects continue working. Existing HA users keep their stored old repository URL. New installs use the new URL. A repository rename does not rename an existing GHCR package; this release uses the separate `d2ha-bridge` package.

The About description and supplied social preview use D2HA Bridge branding. Update those display assets through repository Settings when artwork changes. Preserve existing HA installations and configured repository URLs.

## First GHCR publication

1. Review the changes and commit them on a release branch. Push that branch,
   keeping `main` at the previous release until the image is ready.
2. Enable GitHub Actions for the repository. Permit the workflow's `packages:
   write` permission. It uses the short-lived `GITHUB_TOKEN`; do not add personal
   credentials, broker passwords or registry tokens to source files.
3. Create the annotated Git tag `v3.0.0` at that reviewed commit and push the tag.
   This explicit release action starts CI and, only after all checks and both
   architecture builds pass, publishes images. A manual workflow run with
   `publish: true` is also supported once the workflow is registered on the
   default branch. Ordinary PRs and pushes to `main` never publish images.
4. Check the CI and publishing jobs. The workflow uploads `3.0.0-amd64` and
   `3.0.0-aarch64`, then creates `3.0.0` from their exact digests. Confirm the
   final manifest contains `linux/amd64` and `linux/arm64`. No `latest` tag is
   used. Do not replace an already released version with different source.
5. In GitHub's package settings, set the `d2ha-bridge` container package to
   **Public** and verify its association with this repository. New packages
   can initially be private even when their repository is public.
6. From an unauthenticated environment verify `docker pull --platform
   linux/amd64 ghcr.io/spruben/d2ha-bridge:3.0.0` and the equivalent
   `--platform linux/arm64` pull. An authenticated Actions pull alone is not
   proof that Home Assistant users can download the package.
7. Merge/fast-forward the exact tagged commit into `main`. Refresh the custom
   HA app repository and check installation on both architectures. Keep the legacy app slug and existing configured HA repository URL.
   Existing local installs remain local. Check update-in-place, mappings, MQTT
   entity/device IDs, Ingress and HomeKit before declaring migration success.
8. Create the GitHub Release for existing tag `v3.0.0`. Use
   [the prepared release notes](../release/v3.0.0.md), generated from
   [the app changelog](../dovit_bridge/CHANGELOG.md). Keep it marked as a
   prerelease while the app is experimental and live acceptance is pending.

No workflow creates a GitHub Release automatically. If a publish attempt fails,
leave `main` unchanged and resolve it before inviting installations.

## Local checks and maintenance

Use Python 3.11 with `dovit_bridge/requirements.txt`,
`dovit_bridge/integration_tests/requirements.txt` and
`scripts/requirements-ci.txt`. Run `python scripts/check_repository.py`, then
the complete Python suite from `dovit_bridge` with `python -m unittest discover
-s tests -v`. Run every `tests/*.cjs` file with Node and `node --check` for every
web JavaScript file. MQTT/TLS integration tests opt in with `--run-loopback`
and use disposable loopback brokers only.

CI also builds each image with the matching `BUILD_ARCH` and checks exact
production file hashes, dependencies and restricted startup with
`--network none` and fresh `/data` and `/share` tmpfs mounts. No build/test
contacts a real Dovit endpoint or Home Assistant. Ingress authentication tests
use synthetic DNS answers and loopback HTTP.

The offline startup container maps `supervisor` to the documentation-only
address `192.0.2.2` in its hosts file. This avoids unavailable external DNS
while checking that direct loopback HTTP remains forbidden; it is a test
fixture, not an app configuration or a real Supervisor address.

Update the pinned base tag and its multi-platform digest deliberately for
security maintenance, retaining Python 3.11 unless a separate migration is
reviewed. Run both architecture builds and all tests after such changes.
Pinned images improve repeatability but do not provide security updates by
themselves. Refresh pinned Actions commits deliberately as well.

Generate notes again after any changelog change:
`python scripts/check_repository.py --release-notes release/v3.0.0.md`.
Production inventories and local backups belong outside the public repository.

References: [HA app configuration](https://developers.home-assistant.io/docs/apps/configuration/),
[HA image publication](https://developers.home-assistant.io/docs/apps/publishing/),
[GitHub package visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).
