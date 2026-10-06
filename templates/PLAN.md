# Plan: {plan-name}

<!--
ONE file per planning round. Drop it at the TOP LEVEL of the Proton folder `hub/pm-inbox`
(not in a subfolder). Hub picks it up within 15 minutes and pings the phone ("got it").
The PM then either opens a DEVPLAN pull request (type: features) or checks the plan is
ready to scaffold (type: new-project) and pings you. Any blocking question → you get a
"PM needs you" ping to check in on the PM session.

Fields in the header block are read by the PM. Keep their names exactly.
-->

**Plan type:** new-project | features
**Target repo:** {new-project: proposed repo name, short-hyphenated} | {features: existing active repo, e.g. hub}
**Part:** 1 of 1
**Created:** {YYYY-MM-DD}

## PM Kickoff

<!-- What the PM needs to start without asking. Three to six bullets. -->

- **First action:** {e.g. "scaffold the repo with dtl new, private, then queue the features below" / "add these features after X in hub's DEVPLAN"}
- **Run mode:** overnight | supervised — {overnight = the nightly loop may build these unattended; supervised = the PM builds them in-session with review (security-sensitive, first feature in a new area, or touches credentials, network or hardware)}
- **Operator setup:** {accounts, keys, hardware, BIOS steps the operator must do, and before which feature; "none"}
- **Supersedes / overlaps:** {existing features, repos or FEATURE-REQUESTS entries this replaces or extends; "none"}

## Open Questions

<!--
Questions only the operator can answer. If any line here is marked BLOCKING, the PM does not
start; it pings the operator and waits in a PM session. Non-blocking questions get the stated
default. Write "none" if there are none.
-->

- {BLOCKING | default: <what the PM does if unanswered>} {question}

## Brief

<!-- new-project only. For type: features, delete this whole section. -->

- **Pitch:** {15 words or less}
- **Problem / motivation:** {2–4 sentences}
- **Target user:** {"the operator only" / a persona}. Never a real name.
- **Stack preferences:** {language, data, hosting, LLM; "PM decides" is fine. No hardware models or sizes: say what capability is needed}
- **Must-haves (v1):** {bullets; each maps to features below}
- **Nice-to-haves (later):** {bullets; go to the repo's FEATURE-REQUESTS.md, not the DEVPLAN}
- **Non-goals:** {bullets}
- **Risks & unknowns:** {risk: mitigation}
- **Visibility:** public | private. {Why. Confidentiality only; auto-merge works on both (GitHub Pro).}
- **Hardware target:** {only if it provisions a machine; otherwise "none"}
- **Audience and tone:** {who reads the README}

### Security & Trust Boundaries

<!-- REQUIRED if it touches a network interface beyond localhost, credentials, another device, unattended operation, or metal. Otherwise "none". -->

- **Inbound access:** {Tailnet only / LAN only / none}
- **Credentials held, where:** {GitHub Actions secret / SECRETS USB / systemd credential / Proton Pass}
- **Identity:** {user, service account, token scope}
- **Exposed services + bind address:** {explicit: 127.0.0.1 / tailscale0; never 0.0.0.0; "none"}
- **Trust boundary:** {who trusts whom, one or two lines}
- **Segmentation level:** {same-host containers / separate hardware / fully managed cloud}, {why}

## Constraints

<!-- Rules for every feature below. For type: features, only constraints new to this plan. -->

- {constraint}

## Features

<!--
Same format as the repo's docs/DEVPLAN.md, so the PM copies these blocks in verbatim.
Parseable fields must stay exactly as shown (dtl reads them by regex).
-->

## Feature: {feature-name}

**Branch:** `feature/{feature-name}`
**Depends on:** {feature name, an existing repo feature, or "none"}
**Status:** Not Started
**Requires:** ai | human | both

### Goal

{1–2 sentences.}

### Acceptance Criteria

- [ ] {A check that EXECUTES the real thing: run the CLI and check its exit code and output, parse the real file, call the unit. Never "the file contains X".}
- [ ] [HUMAN] {operator step, if any}
- [ ] All tests pass
- [ ] Lint clean

### Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `path/to/file` | Create | {what it does} |

### Key Decisions

- {decision}: {why}

### Notes

{Gotchas, sources, links. Delete if none.}
