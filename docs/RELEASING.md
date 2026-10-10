# D2HA Bridge release checks

Keep the app experimental and the GitHub release a prerelease. Do not claim compatibility with every server or infer hardware/HomeKit acceptance from synthetic tests. Verify fresh alarm partition readings after startup/reconnection without physical alarm operations. Keep the unsupported-server fallback unavailable and document the limits of live testing.

1. Review the current changelog, known limitations, private-data exclusions and restorable backups. Keep previous local releases and Git history for rollback.
2. Run the complete Python and Node suites, JavaScript syntax, repository configuration/privacy/link checks, loopback MQTT/TLS integration and Docker builds/startup checks for amd64/aarch64. ARM checks may use emulation and must be described as such.
3. Ensure config.yaml, Docker labels, runtime/UI versions, changelog and release notes match. Generate notes with `python scripts/check_repository.py --release-notes release/v3.1.1.md`.
4. Create a verified timestamped source backup before publication. Push a reviewable branch and require its CI checks to pass. Do not rewrite repository history or remove rollback tags.
5. After publication authorization, push the matching version tag or explicitly dispatch image publication. Confirm successful CI, public multi-architecture GHCR images and anonymous pulls for both architectures before updating main's installable app definition.
6. Merge the checked branch and create a prerelease using the changelog-derived notes. Describe unresolved limitations honestly. Ordinary main/PR workflows do not publish images.
7. Verify public README, package access, release page, version metadata and a fresh remote clone. Older releases may be returned to draft if GitHub permits; preserve their tags, commits and rollback images.

HA deployment requires a current verified backup of the actual source/private data/options/mappings. Keep the accepted local release unchanged, deploy the new version to the same app identity, and compare HA/MQTT/HomeKit identifiers before and after. Never operate physical devices merely to verify a deployment.
