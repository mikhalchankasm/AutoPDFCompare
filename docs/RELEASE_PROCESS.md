# Release Process

This project publishes Windows builds through GitHub Releases.

## Local Verification

Run these commands from the repository root:

```powershell
./scripts/lint.ps1
./scripts/test.ps1
./scripts/package_portable.ps1
pyinstaller --noconfirm PDFCompareLocal.spec
```

Expected local artifacts:
- `dist/PDFCompareLocal.exe`
- `dist_portable/PDFCompareLocal-portable.zip`

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

GitHub Actions builds the EXE and portable ZIP, then attaches both to the tagged release.

## Manual Release Fallback

If Actions is unavailable and `gh` is authenticated:

```powershell
gh release create v<version> `
  dist/PDFCompareLocal.exe `
  dist_portable/PDFCompareLocal-portable.zip `
  --title "PDFCompare Local v<version>" `
  --notes-file docs/releases/v<version>.md `
  --latest
```
