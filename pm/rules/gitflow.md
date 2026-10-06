---
paths:
  - "**"
---
# Gitflow Rules

- All projects follow gitflow: main, develop, feature/*, fix/*, release/*, hotfix/*
- Feature branches are created from develop and merge back to develop via PR
- Never commit directly to main or develop
- Never force-push to main or develop
- PRs are reviewed and merged by the human via GitHub app
- AI developers commit but do NOT push — the host workflow handles push and PR
- Conventional commits: feat:, fix:, docs:, test:, chore:, refactor:
