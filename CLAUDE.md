<!-- GSD:project-start source:PROJECT.md -->
## Project

**Holded TT CLI**

A Python CLI tool (`holded-tt`) that automates time-tracking on [Holded](https://app.holded.com) — a Spanish HR SaaS. The primary use case is bulk-registering work days for a date range with a single command, skipping weekends and public holidays automatically. It handles the full authentication flow (email + 2FA) and persists session cookies for subsequent use.

**Core Value:** `holded-tt track --from YYYY-MM-DD --to YYYY-MM-DD` registers all working days in a range without manual effort — weekends and holidays filtered automatically.

### Constraints

- **Tech Stack**: Python 3.11+, Typer, httpx (sync), tomllib (stdlib) / tomli-w, rich — no alternatives
- **Platform**: Cross-platform (Linux, macOS, Windows); Unix file permissions best-effort
- **Security**: `session.json` contains sensitive cookies — never logged, permissions 0600 best-effort
- **API**: Holded internal API — no official SDK, no versioning guarantees; payloads must match browser behavior exactly
- **Testing**: Unit tests for business logic (date filtering, config parsing, session handling) — no HTTP mocking required
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Already-Decided Stack (do not re-research)
| Technology | Role |
|------------|------|
| Python 3.11+ | Runtime (stdlib `tomllib` requires 3.11) |
| Typer | CLI framework |
| httpx (sync) | HTTP client |
| tomllib (stdlib) | TOML config reads |
| tomli-w | TOML config writes |
| rich | Terminal output |
## Build Backend
| Backend | When to use | Verdict |
|---------|-------------|---------|
| `uv_build` | uv-only workflows, fastest builds, new projects | Good for pure-uv shops |
| `hatchling` | Any workflow (pip, pipx, uv), needs no special frontend, wider compatibility | Recommended here |
## pyproject.toml Structure
### Entry Point Declaration
### Src Layout Directory Structure
## Packaging for pipx / uv tool install
# Local development
# or
# Install as isolated tool (end users)
# Install from local directory (dev/testing)
## Cross-Platform Config Directory
| Platform | `user_config_dir("holded-tt-cli")` returns |
|----------|-----------------------------------------|
| Linux | `~/.config/holded-tt-cli` (respects `$XDG_CONFIG_HOME`) |
| macOS | `~/Library/Application Support/holded-tt-cli` |
| Windows | `C:\Users\<user>\AppData\Roaming\holded-tt-cli` |
## Cross-Platform File Permissions (0600 Best-Effort)
### Pattern
## pytest Setup for Typer CLI Testing
### Dependencies
### Core Pattern
# tests/conftest.py
### Test Examples
# tests/test_cli.py
### Key CliRunner Behaviors to Know
| Behavior | Default | How to change |
|----------|---------|---------------|
| stdout + stderr mixed | `True` | `CliRunner(mix_stderr=False)` |
| Filesystem isolation | None | Pass `isolated_filesystem=True` or use `tmp_path` |
| Exceptions swallowed | `True` | `runner.invoke(app, ..., catch_exceptions=False)` |
| stdin | Empty | Pass `input="text\n"` string |
### Testing with Env Vars
## httpx Sync Patterns
### Client Setup
### Cookie Persistence Pattern
### Redirect Handling
# requests: follows redirects by default
# httpx:    does NOT follow redirects by default
# Wrong — will get 302 silently
# Correct — always set explicitly when redirecting is expected
### multipart/form-data for Auth
### Timeout Configuration
# Recommended: explicit timeout, never rely on default None (infinite wait)
### Exception Handling
## Typer + httpx Gotchas
### Gotcha 1: Exception Swallowing in CliRunner
### Gotcha 2: Typer Exit Codes
- `raise typer.Exit(code=0)` — clean exit
- `raise typer.Exit(code=1)` — error exit
- `raise typer.Abort()` — "Aborted!" message, exit code 1
- Unhandled exception — exit code 1, exception stored in `result.exception`
### Gotcha 3: `invoke_without_command` Default is False
### Gotcha 4: Rich + CliRunner Output Capture
### Gotcha 5: httpx Redirects Are Off by Default
### Gotcha 6: tomllib Opens Files in Binary Mode
# CORRECT
# WRONG — will raise TypeError
## Dependency Versions (as of 2025)
| Package | Minimum version | Notes |
|---------|-----------------|-------|
| typer | `>=0.12` | 0.12 added rich integration by default |
| httpx | `>=0.28` | Stable API; 0.28 is current stable |
| tomli-w | `>=1.1` | Stable; no breaking changes expected |
| rich | `>=13.0` | Stable; 13.x is current major |
| platformdirs | `>=4.2` | Current is 4.x; `user_config_path` available since 3.x |
| hatchling | `>=1.24` | Build-time only; not in runtime deps |
| pytest | `>=8.0` | Dev only |
| pytest-cov | `>=5.0` | Dev only |
## Installation Commands Reference
# Initialize project with uv
# Add runtime dependencies
# Add dev dependencies
# Local editable install (dev)
# Build distribution
# Install as tool (end users, isolated)
# Run tests
## Sources
- uv build backend: https://docs.astral.sh/uv/concepts/build-backend/
- uv project init: https://docs.astral.sh/uv/concepts/projects/init/
- uv tools: https://docs.astral.sh/uv/concepts/tools/
- PyPA pyproject.toml guide: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- Typer testing: https://typer.tiangolo.com/tutorial/testing/
- platformdirs: https://platformdirs.readthedocs.io/
- httpx redirect behavior: https://www.python-httpx.org/compatibility/
- httpx cookie persistence discussion: https://github.com/encode/httpx/discussions/2229
- uv_build vs hatchling comparison: https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f
- thisdavej CLI packaging walkthrough: https://thisdavej.com/packaging-python-command-line-apps-the-modern-way-with-uv/
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
