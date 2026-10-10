# D2HA Bridge artwork

The owner supplied these D2HA Bridge assets. PNG/SVG files are copied unchanged; no logo was invented. [Asset manifest](assets/branding/manifest.json) records source names and SHA256 hashes. Brand colors are navy `#1E293B`, blue `#3B82F6`, teal `#14B8A6`, light gray `#E2E8F0`, slate `#64748B` and white. The UI requests Inter with local system-font fallbacks; the pack contains no font file and no remote font is downloaded.

## Home Assistant app

`icon.png` and `logo.png` are beside `config.yaml` in `d2ha_bridge/`, as [HA expects](https://developers.home-assistant.io/docs/apps/configuration/). Supplied `@2x` variants are included. The asset manifest covers the current app definition. Images are presentation assets and do not affect bridge startup or device identity.

Visual review found that the supplied small 250×100 HA `logo.png` clips the right edge of the word “Bridge”. It is retained unchanged as requested. A corrected owner-supplied export is recommended before final visual acceptance; the README logo and web icon do not have this issue.

## GitHub

The README uses [readme-logo.png](assets/branding/readme-logo.png). Upload [social-preview.png](assets/branding/social-preview.png), 1280×640, in repository **Settings → General → Social preview**. [project-avatar.png](assets/branding/project-avatar.png) is optional artwork; changing the owner's GitHub account avatar is outside this migration.

## Optional HA dashboard

Copy the five dashboard PNGs from `docs/assets/branding/` into your own `/config/www/d2ha_bridge/`: `homepage-header.png`, `logo-light.png`, `logo-dark.png`, `icon-light.png`, `icon-dark.png`. Only these dashboard paths use the new namespace; they do not rename app data or MQTT identities.

Example picture card:

```yaml
type: picture
image: /local/d2ha_bridge/homepage-header.png
tap_action:
  action: none
hold_action:
  action: none
```

This is optional manual dashboard setup. No existing dashboard/automation is replaced, and changes no existing dashboard or automation.

## Web interface

Normal and recovery pages use the supplied icon and favicons through relative, same-origin paths compatible with Ingress. Routes are explicitly allowlisted, subject to the same TCP-peer guard. No generic static directory, external image/font request or new host port is introduced. Layout, controls and status/error meaning remain unchanged.


D2HA Bridge is an independent, unofficial community project.
