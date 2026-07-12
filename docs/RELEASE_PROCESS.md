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

GitHub Actions builds the EXE, portable ZIP, and installer, then attaches all three to the tagged release. The `PDFCompareLocal-setup.exe` asset name must not change — the in-app updater looks it up by that exact name.

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
