<div align="center">
  <h1>Thread Project Linker Skill</h1>
  <p><strong>Bulk-safe Codex thread migration across project directories</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Codex-Skill-111827?style=for-the-badge" alt="Codex Skill" />
    <img src="https://img.shields.io/badge/Python-3.9%2B-2563eb?style=for-the-badge" alt="Python 3.9+" />
    <img src="https://img.shields.io/badge/License-MIT-16a34a?style=for-the-badge" alt="MIT License" />
  </p>
</div>

`thread-project-linker` migrates Codex threads to the correct project by updating both:

- `~/.codex/state_5.sqlite` thread `cwd`
- rollout JSONL `session_meta.payload.cwd`

It supports:

- single-thread reassignment
- bulk migration by old absolute path
- bulk migration by old folder name
- optional deeplink filtering (`codex://threads/<id>`)
- dry-run preview before writing
- rollback behavior for partial failures

## Why this exists

When a thread is attached to the wrong workspace path, Codex project grouping can be wrong.  
This skill gives you a deterministic migration command with verification and backup files.

## Install

Clone into your Codex skills directory:

```bash
git clone https://github.com/xlogix/thread-project-linker-skill.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/thread-project-linker"
```

## Usage

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

Bulk from previous directory path:

```bash
python3 scripts/reassign_thread.py \
  --from /absolute/path/to/old-project \
  --to /absolute/path/to/new-project
```

Bulk from previous folder name:

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

## Safety Notes

- The script writes a backup file per migrated rollout before editing.
- DB updates run in a transaction.
- If a failure occurs during migration, it restores rollout files and DB cwd values.
- Prefer `--dry-run` before large migrations.

## License

MIT. See `LICENSE`.
