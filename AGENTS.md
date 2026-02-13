# Repository Guidelines

## Project Structure & Module Organization
This repository is currently in bootstrap state (no source tree committed yet). Use the structure below as code is added:
- `src/`: application logic for PDF parsing, comparison, and report generation.
- `tests/`: automated tests mirroring `src/` modules.
- `samples/`: small, sanitized sample PDFs for local verification.
- `scripts/`: repeatable developer tasks (setup, lint, test, release).
- `docs/`: design notes, architecture decisions, and user-facing documentation.

Keep generated artifacts (diff outputs, temp files) out of version control; write them to `tmp/` and add it to `.gitignore`.

## Build, Test, and Development Commands
No build pipeline is committed yet. Standardize new automation in `scripts/` and expose consistent commands:
- `./scripts/setup.ps1`: install dependencies and local tooling.
- `./scripts/test.ps1`: run the full test suite.
- `./scripts/lint.ps1`: run static checks and formatting validation.
- `./scripts/run.ps1`: run the app locally against sample inputs.

If you introduce a different toolchain, update this section in the same PR.

## Coding Style & Naming Conventions
Use 4-space indentation and UTF-8 text files. Prefer descriptive names:
- Modules/files: `snake_case` (for Python) or language-default conventions.
- Classes/types: `PascalCase`.
- Functions/variables: `snake_case` or language-default style.

Keep functions focused, avoid hidden side effects, and add comments only where intent is non-obvious.

## Testing Guidelines
Place tests under `tests/` with names like `test_<feature>.py` (or language-equivalent). Include:
- Unit tests for core comparison logic.
- Regression tests for previously fixed PDF edge cases.
- Deterministic fixtures in `samples/` (no sensitive documents).

## Commit & Pull Request Guidelines
No established history exists yet; adopt Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`). Keep commits focused and reviewable.

PRs should include:
- Clear summary of behavior changes.
- Linked issue/task ID (if available).
- Test evidence (command + result).
- Before/after output samples for comparison-related changes.
