# Contributing

## Branch workflow

Do not commit directly to `main` after the first publish. Open a branch, push, and open a pull request.

```bash
git checkout -b feature/your-change
git push -u origin feature/your-change
```

GitHub Actions must pass before merging. The required status check name is **CI success** (aggregates Python 3.11 and 3.12 test jobs).

After the first push, enable branch protection on `main` (require a pull request and **CI success**). See [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md).

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```
