# Changes

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
