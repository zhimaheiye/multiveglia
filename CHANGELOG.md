# Changes

## 0.7.1

- Fix browser OAuth consent failing with `Invalid consent request`: use a strict-origin referrer policy so native form submissions preserve their Origin without exposing URL paths or authorization parameters.
- Allow the validated OAuth callback in the consent page's form-action policy so Chromium can follow the authorization redirect back to the client.
- Keep origin, CSRF and cookie checks enforced, and cover null/foreign origins, missing cookies and incorrect CSRF in regression tests.
- Android remains at 0.7.0; existing phone, sensor and Agent credentials remain valid.

## 0.7.0

Based on Veglia by Evelyn & River, with Windows multi-device sensing and deterministic context fusion.

- Add authenticated HTTP MCP with independent full/read-only API keys.
- Add single-owner OAuth authorization-code flow with PKCE, explicit consent, short-lived access tokens, refresh rotation, replay detection and revocation.
- Enforce server-side permissions for reading activity, capturing screenshots and summoning an app.
- Separate Core, phone, sensor and Agent credentials; support bounded rotation windows.
- Remove embedded personal credentials/default addresses and stop accepting URL query tokens.
- Restore Host/Origin validation, bound request sizes and limit authentication traffic.
- Add clean Windows portable packaging, private local configuration generation and release APK signing support.
- Preserve original upstream attribution and CC BY-NC-SA 4.0 licensing.

This is a self-hosted, single-owner tool. Cloud-client and real-phone acceptance checks are deployment-specific.
