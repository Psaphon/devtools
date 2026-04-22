# Development Plan: {PROJECT_NAME}

**Status:** Draft | In Progress | Complete
**Created:** {DATE}
**Updated:** {DATE}

## Overview

{1-3 sentences: what this project does and why it exists.}

## Constraints

{Non-negotiable rules that apply to ALL features. Security, dependencies, compatibility, etc.}

- {constraint}
- {constraint}

---

## Feature: {feature-name}

**Branch:** `feature/{feature-name}`
**Depends on:** {previous feature branch, or "none"}
**Status:** Not Started | In Progress | PR Open | Merged
**Requires:** ai | human | both

### Goal

{1-2 sentences: what this feature delivers. The AI developer reads this to understand scope.}

### Acceptance Criteria

- [ ] {Testable condition that must be true when the feature is complete}
- [ ] {Another condition}
- [ ] All tests pass (`pytest` / `npm test` / etc.)
- [ ] Lint clean (`ruff check .` / `eslint` / etc.)

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/thing.py` | Create | {what it does} |
| `src/main.py` | Modify | {what changes} |
| `tests/test_thing.py` | Create | {what it tests} |

### Key Decisions

{Design choices the AI should follow, not invent. Skip if obvious.}

- {decision}: {why}

### Assets

<!-- Optional. Use when this feature produces non-code deliverables: workflow JSONs, prompts, reference images, audio samples, model weights, etc. Skip for pure-code features. -->

| Asset | Location | Format | Purpose |
|-------|----------|--------|---------|
| `{filename}` | `{path/}` | {JSON / PNG / safetensors / …} | {what it's for} |

### Notes

{Gotchas, edge cases, external API quirks, links to docs. Skip if none.}

---

<!-- Copy the "Feature" block above for each feature branch. -->
<!-- Each feature should be mergeable independently and leave the project working. -->
<!-- Order features so each builds on the last — minimize merge conflicts. -->
<!-- Requires field: "ai" = fully automated, "human" = manual setup/config, "both" = AI codes but human does setup steps -->
<!-- For "both" features, prefix human-required acceptance criteria with [HUMAN] -->
