---
description: Prepare the next AI development session for a project
argument-hint: [project-name]
---

For the project `$ARGUMENTS` under ~/Projects:

1. Read `docs/DEVPLAN.md` and find the next feature where:
   - Status is "Not Started" or "In Progress"
   - Requires includes "ai"
   - All dependencies are "Complete"

2. Check git state:
   - Is develop up to date with origin?
   - Any uncommitted changes?
   - Any stale feature branches to clean up?

3. Check if an AI prompt file already exists in `docs/AI_PROMPT_*.md` for this feature.
   - If yes, review it for accuracy against current codebase
   - If no, create one following the template in CLAUDE.md

4. Output the exact commands the human needs to run:
   ```
   cd ~/Projects/<project>
   git checkout develop && git pull origin develop
   git checkout -b <branch>
   dtl ai run --project ~/Projects/<project> --prompt "$(cat docs/AI_PROMPT_<feature>.md)"
   ```
