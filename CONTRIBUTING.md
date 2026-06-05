# Contributing to Ahy Governance

Thanks for contributing. This guide covers everything you need to get started.

## Table of Contents

- [Development Environment](#development-environment)
- [Commit Conventions](#commit-conventions)
- [Pull Request Workflow](#pull-request-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)

## Development Environment

```bash
# Clone and set up
git clone https://github.com/Leo-Ayh-Oday/ahy-governance.git
cd ahy-governance

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS/Linux

# Install in dev mode with all extras
pip install -e ".[web,postgres,redis,security,crewai,mcp,observability]"
pip install pytest pytest-cov ruff bandit
```

Run the dashboard to verify setup:

```bash
ahy-dashboard
# Open http://localhost:8081
```

## Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

feat: add conflict auto-resolution for scope conflicts
fix: correct cost attribution when agent uses multiple models
docs: update MCP integration guide
test: add coverage for self-healing recovery rules
refactor: extract hash chain logic from audit reporter
chore: bump fastmcp to 3.x
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`, `ci`

## Pull Request Workflow

1. **Fork and branch** — create a feature branch from `main`
2. **Implement** — follow the code style and add tests
3. **Self-review** — check against the checklist below
4. **Run tests** — `pytest tests/ -v --cov=ahy_governance --cov-report=term`
5. **Open PR** — fill out the PR template, link related issues
6. **CI must pass** — tests, lint, bandit, coverage gate (80%+)

### PR Checklist

- [ ] Tests added for new functionality
- [ ] Existing tests pass (`pytest tests/`)
- [ ] Ruff lint clean (`ruff check .`)
- [ ] Coverage at or above 80%
- [ ] No hardcoded secrets or credentials
- [ ] Documentation updated if needed
- [ ] Commit messages follow conventional commits format

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Config is in `pyproject.toml`:

- Target: Python 3.10+
- Line length: 100
- Rules: E, F, W, I, N, UP, B, SIM

```bash
ruff check .       # lint
ruff check --fix . # auto-fix
```

### Style Guidelines

- **Functions** — keep under 50 lines where practical
- **Files** — keep under 800 lines, extract modules when they grow
- **Immutability** — prefer returning new objects over mutating in-place
- **Type hints** — use for public APIs, optional for internal helpers
- **Docstrings** — required for public modules, classes, and functions
- **Early returns** — prefer over deep nesting

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=ahy_governance --cov-report=term --cov-report=html

# Run specific test file
pytest tests/test_conflict_detector.py -v

# Run with bandit security scan
bandit -r ahy_governance/ -ll
```

### Test Structure

```
tests/
├── test_conflict_detector.py
├── test_cost_tracker.py
├── test_audit_reporter.py
├── test_health_monitor.py
├── test_auth_rbac.py
├── test_self_healer.py
├── test_mcp_server.py
└── ...
```

Tests use AAA pattern (Arrange → Act → Assert). Use descriptive test names that explain the behavior under test.

```python
def test_conflict_detector_flags_scope_mismatch_between_two_agents():
    # Arrange
    detector = ConflictDetector()
    agent1_output = {"scope": "read_only"}
    agent2_output = {"scope": "write"}

    # Act
    conflicts = detector.check(agent1_output, agent2_output)

    # Assert
    assert len(conflicts) == 1
    assert conflicts[0].type == "scope"
```

## Documentation

- **User-facing docs** — update `README.md` and `docs/`
- **API docs** — docstrings on public functions, Google-style
- **Changelog** — add entries to `CHANGELOG.md` under `[Unreleased]`

## Getting Help

- **Questions** — [GitHub Discussions](https://github.com/Leo-Ayh-Oday/ahy-governance/discussions)
- **Bugs** — [GitHub Issues](https://github.com/Leo-Ayh-Oday/ahy-governance/issues)
- **Security** — see [SECURITY.md](SECURITY.md)
