# Repository Guidelines

## Project Structure & Module Organization

Production code lives in `src/codex_usage_widget/` and `src/claude_usage_widget/`, automated tests in `tests/`, static Windows packaging resources in `assets/`, and build helpers in `scripts/`. Group modules by feature rather than file type. Do not commit generated output, dependency caches, credentials, local usage caches, or editor-specific files; keep them in `.gitignore`.

## Build, Test, and Development Commands

- `.\.venv\Scripts\python.exe -m codex_usage_widget` — run the widget from source.
- `.\.venv\Scripts\python.exe -m claude_usage_widget` — run the Claude widget from source.
- `.\.venv\Scripts\python.exe -m pytest` — run unit, protocol, and Qt tests.
- `.\.venv\Scripts\python.exe -m ruff check .` — run static lint checks.
- `.\.venv\Scripts\python.exe -m ruff format .` — format Python source.
- `.\scripts\build.ps1` — test, lint, generate the icon, and build the single-file EXE.
- `.\scripts\build-claude.ps1` — test, lint, generate the Claude icon, and build its single-file EXE.
- `git diff --check` — detect whitespace errors before committing.

## Coding Style & Naming Conventions

Use UTF-8 files, LF line endings, a final newline, and spaces instead of tabs unless the selected language mandates otherwise. Prefer the ecosystem's standard formatter and linter, committed with project configuration. Use descriptive names: `PascalCase` for types, `camelCase` for functions and variables, and `kebab-case` for documentation and asset filenames. Keep functions focused and avoid unrelated formatting changes.

## Testing Guidelines

Every behavior change should include an automated test. Mirror the `src/` layout under `tests/`, or use the language's conventional colocated test structure. Name tests after observable behavior, such as `user-session.test.ts` or `test_user_session.py`. Bug fixes should include a regression test. Document any intentionally untested path in the pull request.

## Commit & Pull Request Guidelines

There is no commit history from which to infer a convention. Use concise Conventional Commit subjects, for example `feat: add session timeout` or `fix: reject invalid tokens`. Keep each commit focused. Pull requests should explain the problem, summarize the solution, list verification performed, and link relevant issues. Include screenshots or terminal output when UI or operational behavior changes.

## Security & Configuration

Keep secrets in environment variables, never in tracked files. Provide sanitized examples such as `.env.example`, document required settings, and review new dependencies for necessity and maintenance status.
