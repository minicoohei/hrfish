# Contributing to MiroFish

Thank you for your interest in contributing to MiroFish! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker & Docker Compose (optional, for containerized setup)

### Backend

```bash
cd backend
uv sync
cp .env.example .env  # configure your environment variables
uv run python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker (full stack)

```bash
docker compose up
```

## Running Tests

```bash
cd backend
uv run pytest
```

To run a specific test file:

```bash
uv run pytest tests/test_example.py -v
```

## How to Contribute

### 1. Fork & Clone

```bash
git clone https://github.com/<your-username>/MiroFish.git
cd MiroFish
```

### 2. Create a Branch

```bash
git checkout -b feat/your-feature-name
```

Use prefixes: `feat/`, `fix/`, `docs/`, `refactor/`, `test/`.

### 3. Make Changes

- Write clear, descriptive commit messages.
- Add tests for new functionality.
- Ensure all existing tests pass.

### 4. Submit a Pull Request

1. Push your branch to your fork.
2. Open a PR against the `main` branch.
3. Fill in the PR template with a clear description.
4. Link any related issues.

A maintainer will review your PR. Please be patient and responsive to feedback.

## Code Style

### Python (backend)

- Follow existing patterns in the codebase.
- Use type hints where practical.
- Keep functions focused and well-named.
- Use `async/await` consistently for async endpoints.

### JavaScript (frontend)

- Follow existing patterns in the codebase.
- Use Vue 3 Composition API for new components.
- Keep components small and composable.

## Reporting Bugs

Open a [GitHub Issue](https://github.com/666ghj/MiroFish/issues) with:

- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python/Node version)

## Security Vulnerabilities

Please do **not** open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
