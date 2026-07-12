# Release Process

This project publishes Windows builds through GitHub Releases.

## Local Verification

Run these commands from the repository root:

```powershell
./scripts/lint.ps1
./scripts/test.ps1
./scripts/package_portable.ps1
pyinstaller --noconfirm packaging/PDFCompareLocal.spec
# Installer (requires Inno Setup 6; CI builds it automatically):
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=<version> packaging/installer.iss
```

Expected local artifacts:
- `dist/PDFCompareLocal.exe`
- `dist_portable/PDFCompareLocal-portable.zip`
- `dist_installer/PDFCompareLocal-setup.exe` (per-user installer; the app auto-updates by downloading this asset and running it with `/SILENT`)

## Tagged Release

1. Update `APP_VERSION` in `pdfcompare_core/constants.py`.
2. Update `README.md`, `CHANGELOG.md`, and `docs/releases/v<version>.md`.
3. Commit the release changes.
4. Create and push a tag:

```powershell
git tag v<version>
git push origin master
git push origin v<version>
```

GitHub Actions builds the EXE, portable ZIP, and installer, then attaches them to the tagged release together with `SHA256SUMS.txt`. Asset names must not change: the in-app updater looks up `PDFCompareLocal-setup.exe` by exact name and refuses to auto-install unless its SHA-256 matches the manifest (releases without the manifest fall back to opening the download page).

Authenticode signing is a deliberate non-goal for now (personal/friends distribution; a code-signing certificate costs money and SmartScreen warnings are acceptable). If the audience widens, add signtool to the build job and publisher verification to the updater.

## Manual Release Fallback

If Actions is unavailable and `gh` is authenticated:

```powershell
gh release create v<version> `
  dist/PDFCompareLocal.exe `
  dist_portable/PDFCompareLocal-portable.zip `
  dist_installer/PDFCompareLocal-setup.exe `
  --title "PDFCompare Local v<version>" `
  --notes-file docs/releases/v<version>.md `
  --latest
```
