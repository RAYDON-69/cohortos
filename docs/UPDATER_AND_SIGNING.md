# Updater & code signing (P36 C2)

## Current state
**No auto-updater is wired.** Desktop builds are manual GitHub Releases artifacts from `desktop-package.yml` / `desktop-release.yml`.

## Manual update path
1. Download installer from GitHub Releases for the tag
2. Verify checksum: `SHA256SUMS` file attached to the release
3. Install over previous version (SQLite data dirs are outside the install tree)

## When auto-update is added
Must use signature verification (electron-updater + code-signed artifacts, or minisign/cosign on the payload). Tests must prove:
- unsigned update rejected
- downgrade rejected
- valid signature accepted

## Code signing cost options (NOT-DONE)
| Platform | Option | Approx cost |
|----------|--------|-------------|
| Windows | Authenticode EV cert | ~$300–400/yr |
| Windows | Standard OV cert | ~$200/yr + identity check |
| macOS | Apple Developer ID | $99/yr |
| Linux | same binary + GPG/minisign | free |

SmartScreen reputation still needs volume or EV.
