# Release preparation 3.1.0

3.1.0 is the separate Phase 2 app identity. The complete 3.0.0 app definition and released image remain unchanged for rollback. This candidate is not yet published; do not advertise a usable 3.1 store entry until its images are publicly verified. Actual HA migration acceptance remains pending, so retain experimental/prerelease status.

## Validate and prepare

1. Review the [migration procedure](MIGRATION_3_1.md), private data access, current complete HA backup and single-bridge rollback. Private bundles and real mappings must never enter the public repository/images/Actions artifacts.
2. Run `python scripts/check_repository.py --app dovit_bridge` and `python scripts/check_repository.py --app d2ha_bridge`. Both apps retain frozen compatibility surfaces; the 135 legacy app files are checked byte-for-byte. Do not disable the Phase 1 legacy slug guard.
3. Run the complete Python suite, all Node suites and JS syntax checks from each app folder. The new app adds synthetic stopped-snapshot transfer, error, identity, archive and rollback checks. Run both existing isolated MQTT/TLS integration suites with disposable loopback brokers.
4. Build the **new** app from `d2ha_bridge` for `linux/amd64` and `linux/arm64`, passing matching `BUILD_ARCH` and `BUILD_VERSION=3.1.0`. Verify exact production inventories/dependencies/restricted startup with `--network none`, fresh `/data` and `/share` tmpfs and documentation-only Supervisor DNS. ARM may use emulation; record that limit.
5. Generate [release notes](../release/v3.1.0.md) from [the new changelog](../d2ha_bridge/CHANGELOG.md): `python scripts/check_repository.py --release-notes release/v3.1.0.md`. Review diff/privacy, create a fresh verified local backup, then commit the release branch. Preserve all previous tags/releases and the existing repository ID/history.

## Publication after authorization

1. Push the reviewed release branch and check PR CI. Keep main on its previous usable release until replacement images exist. No personal credentials or new repository secrets are required.
2. Create annotated `v3.1.0` at the exact tested commit and push that tag, or explicitly dispatch CI with `publish: true`. Ordinary PR/main runs never publish. Tag/version must match the **new** app. Publishing is a separate authorized release action; preparation does not perform it.
3. CI tests both app definitions and builds the new app on amd64/aarch64. Publish `ghcr.io/spruben/d2ha-bridge:3.1.0-amd64` and `:3.1.0-aarch64`, then create the exact-digest `:3.1.0` manifest. Do not overwrite 3.0.0 or add a moving latest tag.
4. Confirm package Public/repository association and anonymously pull both architectures using an empty Docker auth environment. Verify labels, content, dependencies and isolated startup. Authenticated Actions success alone does not establish HA download access.
5. Merge the exact reviewed/tagged source to main. Both legacy `dovit_bridge` and new `d2ha_bridge` definitions stay present. Existing configured HA repository URLs remain unchanged; local installations remain local. The new default is manual boot. Never start both bridges against the same home.
6. Create the GitHub prerelease for existing tag `v3.1.0` using the generated notes. CI does not create a GitHub Release. Report real HA/Ingress/Dovit/MQTT/entity/HomeKit tests accurately; offline tests are not live acceptance.

The HA `image` field pulls the tag selected by the app's version. Missing/private 3.1 images do not fall back to a local build. An explicitly prepared **private local** deployment variant omits only that image reference and uses the same empty public seed; it must not be published as a household image.

## Security maintenance

The pinned Python 3.11.17/Alpine 3.23 multi-arch digest, Paho 2.1.0 and pinned CI Actions are retained. Update them deliberately with full verification when needed; version pinning does not itself deliver future security updates. Ingress remains internal, with no host ports and a dynamically resolved Supervisor peer guard. No additional HA/Docker privileges are introduced.

References: [HA app configuration](https://developers.home-assistant.io/docs/apps/configuration/), [HA image publication](https://developers.home-assistant.io/docs/apps/publishing/), [package visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).
