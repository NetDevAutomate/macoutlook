---
title: "CI and Pre-commit Pipeline Fixes with Git Identity Remediation"
date: 2026-03-14
category: build-errors
severity: high
components:
  - pyproject.toml
  - .pre-commit-config.yaml
  - .github/workflows/ci.yml
  - git-config
  - src/macoutlook
symptoms:
  - "ruff: Failed to spawn - No such file or directory in CI"
  - "mypy: 258 errors from --strict flag in pre-commit isolated venv"
  - "bandit: pass_filenames conflicting with -r src/ positional args"
  - "detect-secrets: missing or incompatible baseline file"
  - "git commits attributed to wrong email addresses"
root_causes:
  - "dev tools in [project.optional-dependencies] not installed by uv sync --dev"
  - "pre-commit mypy --strict overriding pyproject.toml config in isolated venv"
  - "bandit pass_filenames: true conflicting with hardcoded -r src/ argument"
  - "git user.email not pinned; ansible-managed global config had wrong identity"
tags:
  - uv
  - ruff
  - mypy
  - bandit
  - detect-secrets
  - pre-commit
  - github-actions
  - git-identity
  - dependency-management
---

# CI and Pre-commit Pipeline Fixes

## Problem Summary

After initial development, the GitHub Actions CI workflow failed with `Failed to spawn: ruff` and `pre-commit run --all-files` produced failures across multiple hooks. Additionally, git commits were attributed to wrong identities across machines.

## Root Cause Analysis & Solutions

### 1. CI `ruff` Not Found

**Symptom**: `uv run ruff check .` → `Failed to spawn: ruff - No such file or directory`

**Root cause**: Dev tools were in `[project.optional-dependencies] dev` but CI ran `uv sync --dev` which installs `[dependency-groups] dev` (PEP 735). These are different sections with different semantics.

**Fix**: Move dev tooling to `[dependency-groups]`, regenerate lockfile.

```toml
# BEFORE (broken) — optional-dependencies are for pip install macoutlook[dev]
[project.optional-dependencies]
dev = ["ruff>=0.1.0", "mypy>=1.5.0", "pre-commit>=3.4.0"]

[dependency-groups]
dev = ["pytest-cov>=4.1.0"]

# AFTER (fixed) — dependency-groups are for uv sync --dev
[dependency-groups]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "pre-commit>=3.4.0",
]
```

### 2. Pre-commit mypy with `--strict`

**Symptom**: 258 mypy errors including test files, scripts, and strict-mode violations.

**Root cause**: `mirrors-mypy` ran in an isolated venv without project dependencies, and `--strict` overrode the nuanced per-module config in `pyproject.toml`.

**Fix**: Replace with local hook using project venv.

```yaml
# BEFORE — isolated venv, wrong flags
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.19.1
  hooks:
    - id: mypy
      args: [--strict, --ignore-missing-imports]

# AFTER — uses project venv and pyproject.toml config
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: uv run mypy src/
      language: system
      types: [python]
      pass_filenames: false
      always_run: true
```

### 3. Bandit `pass_filenames` Conflict

**Symptom**: `bandit: error: unrecognized arguments` followed by a list of Python files.

**Root cause**: Default `pass_filenames: true` appended file paths as positional args alongside `-r src/`, which bandit couldn't parse.

**Fix**: Set `pass_filenames: false`, add `# nosec` for false positives.

```yaml
- id: bandit
  args: [-r, src/]
  pass_filenames: false
```

```python
# Suppress false positives on allowlisted table names
query = f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608  # nosec B608
```

### 4. Type Annotation Fixes

**Symptom**: mypy errors on list invariance, untyped params, wrong ignore codes.

**Fixes applied**:
- `cli/main.py`: `list[object]` → `Sequence[Any]` (list is invariant)
- `icalendar.py`: Added `Any` annotations to icalendar component params
- `client.py`: `type: ignore[arg-type]` → `type: ignore[call-overload]`

### 5. Git Identity Contamination

**Symptom**: GitHub showed 4 contributors including `ataylor` and `taylaand` instead of just `Andy Taylor`.

**Root cause**: Global `~/.gitconfig` had wrong email, pre-commit template enforced wrong identity, ansible `group_vars` perpetuated old email.

**Fix**: Multi-layer approach:
1. `git filter-branch --env-filter` to rewrite all commit history
2. Delete and recreate GitHub repo (force-push doesn't clear contributor cache)
3. Pre-commit hook to block commits with wrong identity
4. Update global git config, ansible vars, `repo_init()` function

## Prevention Strategies

### uv Dependency Management
- **`[dependency-groups]`** for dev-only tooling (never shipped)
- **`[project.optional-dependencies]`** only for user-facing extras
- Document the distinction with inline comments in `pyproject.toml`

### Pre-commit Best Practices
- **Never use `mirrors-mypy`** — it lacks your project's type stubs
- **Use `language: system` with `uv run`** for tools needing project deps
- **Set `pass_filenames: false`** for tools that need whole-project context
- **Test with `pre-commit run --all-files`** after any config change
- **Keep hooks fast** (<10s) — move slow checks to CI only

### Git Identity Management
- Set identity at repo level via `repo_init()` function
- Pre-commit hook validates `user.email` before every commit
- Global config as fallback, not primary
- Audit with `git log --format='%ae' | sort -u` periodically

## Cross-References

- [CONTRIBUTING.md](../../../CONTRIBUTING.md) — Developer setup instructions
- [CI workflow](../../../.github/workflows/ci.yml) — GitHub Actions config
- [Pre-commit config](../../../.pre-commit-config.yaml) — Hook definitions
