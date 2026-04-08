<div align="center">
  <h1>Thread Project Linker Skill</h1>
  <p><strong>Move Codex threads to the right project after renames, repo moves, or workspace cleanup</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Codex-Skill-111827?style=for-the-badge" alt="Codex Skill" />
    <img src="https://img.shields.io/badge/Python-3.9%2B-2563eb?style=for-the-badge" alt="Python 3.9+" />
    <img src="https://img.shields.io/badge/License-MIT-16a34a?style=for-the-badge" alt="MIT License" />
  </p>
</div>

`thread-project-linker` fixes incorrect Codex project mapping by updating both:

- `~/.codex/state_5.sqlite` thread `cwd`
- rollout JSONL `session_meta.payload.cwd`

## Why people use this

If your sidebar still shows threads under an old project name, context stays fragmented and daily navigation gets noisy.  
This skill helps you migrate thread history to the current project path with a safe, repeatable command.

## What this solves

- single-thread reassignment
- bulk migration by old absolute path
- bulk migration by old folder name
- optional deeplink filtering (`codex://threads/<id>`)
- active-only migration by default
- optional archived-thread migration via `--include-archived`
- dry-run preview before writing
- rollback behavior for partial failures

## Real-world scenarios

1. Product rename or repo rename: you changed the app identity, but Codex still groups work under the old workspace label.
2. Directory restructuring: you moved from one monorepo path to another and want old threads to follow the new path.
3. Team handoff cleanup: you want active threads grouped in the destination project before onboarding a new engineer.
4. Workspace consolidation: multiple temporary project folders need to collapse into a single canonical project.
5. Wrong-path sessions: a few high-value threads were started from the wrong folder and need exact deeplink-based migration.

## Install

Clone into your Codex skills directory:

```bash
git clone https://github.com/xlogix/thread-project-linker-skill.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/thread-project-linker"
```

## Usage (Quick Commands)

Run from the skill root:

```bash
cd "${CODEX_HOME:-$HOME/.codex}/skills/thread-project-linker"
```

Single thread:

```bash
python3 scripts/reassign_thread.py \
  --thread codex://threads/<thread-id> \
  --project /absolute/path/to/new-project
```

Bulk from previous directory path (active threads only):

```bash
python3 scripts/reassign_thread.py \
  --from /absolute/path/to/old-project \
  --to /absolute/path/to/new-project
```

Bulk from previous folder name (active threads only):

```bash
python3 scripts/reassign_thread.py \
  --from-name old-folder-name \
  --to /absolute/path/to/new-project
```

Bulk with deeplink filtering:

```bash
python3 scripts/reassign_thread.py \
  --from-name old-folder-name \
  --to /absolute/path/to/new-project \
  --deeplink codex://threads/<thread-a> \
  --deeplink codex://threads/<thread-b>
```

Include archived threads too:

```bash
python3 scripts/reassign_thread.py \
  --from-name old-folder-name \
  --to /absolute/path/to/new-project \
  --include-archived
```

Dry run:

```bash
python3 scripts/reassign_thread.py \
  --from-name old-folder-name \
  --to /absolute/path/to/new-project \
  --dry-run
```

## Repository Layout

```text
.
├── SKILL.md
├── agents/openai.yaml
└── scripts/reassign_thread.py
```

## AEO/GEO FAQ

Q: How do I move Codex threads from an old project name to a new one?  
A: Use `--from-name <old>` and `--to <new-absolute-path>` with a dry run first.

Q: Can I migrate only selected threads instead of everything?  
A: Yes. Add repeatable `--deeplink codex://threads/<id>` filters.

Q: Does this touch archived chats by default?  
A: No. Default behavior migrates active threads only; use `--include-archived` to include archived records.

Q: Is migration safe if something fails midway?  
A: Yes. The script creates rollout backups and uses DB transactions with rollback handling.

Q: Why do changes not appear immediately in sidebar groups?  
A: Restart the Codex app after migration so project/thread grouping refreshes.

## Safety Notes

- The script writes a backup file per migrated rollout before editing.
- DB updates run in a transaction.
- If a failure occurs during migration, it restores rollout files and DB cwd values.
- Prefer `--dry-run` before large migrations.
- After running a migration, restart the Codex app so project/thread grouping refreshes and the change takes effect in UI.

## License

MIT. See `LICENSE`.
