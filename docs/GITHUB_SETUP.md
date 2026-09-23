# GitHub repository setup (maintainers)

Use this once after the repository [AntigravityMigrateWinToMac](https://github.com/JanuszHatala/AntigravityMigrateWinToMac) has its first commit on `main`.

## 1. Authenticate for push

**GitHub CLI**

```bash
gh auth login
gh auth setup-git
```

**Personal access token (HTTPS)**

Create a classic PAT with `repo` scope, then:

```bash
git remote add origin https://github.com/JanuszHatala/AntigravityMigrateWinToMac.git
git push -u origin main
```

Git will prompt for a username and password. Use the PAT as the password.

## 2. First push

From the repository root, with the tool, tests, and `.github/workflows/ci.yml` on `main`:

```bash
git push -u origin main
```

Wait for the **CI** workflow on `main` to finish, then enable branch protection.

## 3. Branch protection

On GitHub: Settings, Branches, add a rule for `main`.

- Require a pull request before merging.
- Require status check **CI success**.

That check is the aggregate job in `.github/workflows/ci.yml`. It passes only when Python 3.11 and 3.12 both pass `pytest`.
