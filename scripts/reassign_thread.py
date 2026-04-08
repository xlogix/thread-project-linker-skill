#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


THREAD_PREFIX = 'codex://threads/'


def parse_thread_id(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith(THREAD_PREFIX):
        candidate = candidate[len(THREAD_PREFIX) :]
    if not candidate:
        raise ValueError('Thread ID is empty.')
    return candidate


def normalized_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def load_first_session_meta(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as src:
        first_line = src.readline()
    if not first_line:
        raise RuntimeError(f'Rollout file is empty: {path}')
    try:
        first_obj = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Failed to parse first JSONL line in {path}: {exc}') from exc

    if first_obj.get('type') != 'session_meta':
        raise RuntimeError(f'First JSONL entry is not session_meta in {path}')
    return first_obj


def update_rollout_session_meta_cwd(rollout_path: Path, thread_id: str, new_cwd: str) -> Path:
    if not rollout_path.exists():
        raise FileNotFoundError(f'Rollout file not found: {rollout_path}')

    timestamp = int(time.time())
    backup_path = rollout_path.with_suffix(rollout_path.suffix + f'.{thread_id}.bak.{timestamp}')
    shutil.copy2(rollout_path, backup_path)

    with rollout_path.open('r', encoding='utf-8') as src:
        first_line = src.readline()
        if not first_line:
            raise RuntimeError('Rollout file is empty; cannot update session metadata.')

        try:
            first_obj = json.loads(first_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'Failed to parse first JSONL line: {exc}') from exc

        if first_obj.get('type') != 'session_meta':
            raise RuntimeError('First JSONL entry is not session_meta; refusing to edit.')

        payload = first_obj.get('payload') or {}
        if payload.get('id') != thread_id:
            raise RuntimeError(
                f"Session metadata thread id mismatch: expected '{thread_id}', got '{payload.get('id')}'."
            )

        payload['cwd'] = new_cwd
        first_obj['payload'] = payload

        fd, temp_path = tempfile.mkstemp(prefix='thread-project-linker-', suffix='.jsonl')
        try:
            with open(fd, 'w', encoding='utf-8', closefd=True) as dst:
                dst.write(json.dumps(first_obj, ensure_ascii=False, separators=(',', ':')) + '\n')
                shutil.copyfileobj(src, dst)
            shutil.move(temp_path, rollout_path)
        finally:
            if Path(temp_path).exists():
                Path(temp_path).unlink(missing_ok=True)

    return backup_path


def fetch_thread_rows(cur: sqlite3.Cursor, thread_ids: list[str], include_archived: bool) -> list[dict]:
    rows: list[dict] = []
    missing: list[str] = []
    skipped_archived: list[str] = []
    for thread_id in thread_ids:
        row = cur.execute(
            'SELECT id, cwd, rollout_path, archived FROM threads WHERE id = ?',
            (thread_id,),
        ).fetchone()
        if row is None:
            missing.append(thread_id)
            continue
        row_id, cwd, rollout_path, archived = row
        if archived and not include_archived:
            skipped_archived.append(thread_id)
            continue
        if not rollout_path:
            raise RuntimeError(f"Thread '{row_id}' has no rollout path.")
        rows.append(
            {
                'id': row_id,
                'old_cwd': cwd,
                'rollout_path': rollout_path,
                'archived': bool(archived),
            }
        )

    if missing:
        raise RuntimeError(f'Threads not found in state DB: {", ".join(missing)}')
    if skipped_archived:
        raise RuntimeError(
            'Archived threads are excluded by default. Re-run with --include-archived: '
            + ', '.join(skipped_archived)
        )
    return rows


def fetch_rows_by_old_cwd(cur: sqlite3.Cursor, old_cwd: str, include_archived: bool) -> list[dict]:
    if include_archived:
        results = cur.execute(
            'SELECT id, cwd, rollout_path, archived FROM threads WHERE cwd = ? ORDER BY updated_at DESC',
            (old_cwd,),
        ).fetchall()
    else:
        results = cur.execute(
            'SELECT id, cwd, rollout_path, archived FROM threads WHERE cwd = ? AND archived = 0 ORDER BY updated_at DESC',
            (old_cwd,),
        ).fetchall()
    return [
        {
            'id': row_id,
            'old_cwd': cwd,
            'rollout_path': rollout_path,
            'archived': bool(archived),
        }
        for row_id, cwd, rollout_path, archived in results
    ]


def fetch_rows_by_old_folder_name(cur: sqlite3.Cursor, folder_name: str, include_archived: bool) -> list[dict]:
    if include_archived:
        results = cur.execute(
            'SELECT id, cwd, rollout_path, archived FROM threads WHERE cwd = ? OR cwd LIKE ? ORDER BY updated_at DESC',
            (folder_name, f'%/{folder_name}'),
        ).fetchall()
    else:
        results = cur.execute(
            'SELECT id, cwd, rollout_path, archived FROM threads WHERE (cwd = ? OR cwd LIKE ?) AND archived = 0 ORDER BY updated_at DESC',
            (folder_name, f'%/{folder_name}'),
        ).fetchall()
    return [
        {
            'id': row_id,
            'old_cwd': cwd,
            'rollout_path': rollout_path,
            'archived': bool(archived),
        }
        for row_id, cwd, rollout_path, archived in results
    ]


def update_db_cwd_bulk(db_path: Path, rows: list[dict], new_cwd: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('BEGIN')
        for row in rows:
            conn.execute(
                "UPDATE threads SET cwd = ?, updated_at = CAST(strftime('%s','now') AS INTEGER) WHERE id = ?",
                (new_cwd, row['id']),
            )
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.close()


def restore_db_old_cwds(db_path: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('BEGIN')
        for row in rows:
            conn.execute(
                "UPDATE threads SET cwd = ?, updated_at = CAST(strftime('%s','now') AS INTEGER) WHERE id = ?",
                (row['old_cwd'], row['id']),
            )
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise
    finally:
        conn.close()


def restore_rollout_files(backup_map: dict[str, dict]) -> None:
    for record in backup_map.values():
        backup = record['backup']
        path = record['path']
        if backup.exists():
            shutil.copy2(backup, path)


def verify(db_path: Path, rows: list[dict], expected_cwd: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for row in rows:
            db_row = conn.execute(
                'SELECT cwd FROM threads WHERE id = ?',
                (row['id'],),
            ).fetchone()
            if db_row is None or db_row[0] != expected_cwd:
                raise RuntimeError(f"Verification failed: DB cwd mismatch for thread '{row['id']}'.")
    finally:
        conn.close()

    for row in rows:
        first_obj = load_first_session_meta(Path(row['rollout_path']))
        payload = first_obj.get('payload') or {}
        file_cwd = payload.get('cwd')
        if payload.get('id') != row['id']:
            raise RuntimeError(f"Verification failed: session_meta id mismatch in thread '{row['id']}'.")
        if file_cwd != expected_cwd:
            raise RuntimeError(f"Verification failed: rollout cwd mismatch for thread '{row['id']}'.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Reassign one or many Codex threads to a different project cwd and keep metadata in sync.'
    )
    parser.add_argument(
        '--thread',
        action='append',
        default=[],
        help='Thread ID or codex://threads/<id> URI. Repeatable.',
    )
    parser.add_argument(
        '--deeplink',
        action='append',
        default=[],
        help='codex://threads/<id> deeplink. Repeatable; same as --thread.',
    )
    parser.add_argument('--project', help='Target project path when migrating selected thread IDs.')
    parser.add_argument('--from', dest='from_path', help='Source project path for bulk migration.')
    parser.add_argument(
        '--from-name',
        help='Source folder name (basename match on cwd) for bulk migration, e.g. crewbridge.',
    )
    parser.add_argument('--to', help='Target project path for bulk migration.')
    parser.add_argument(
        '--codex-home',
        default=str(Path.home() / '.codex'),
        help='Codex home directory (default: ~/.codex).',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate and print what would change without writing.',
    )
    parser.add_argument(
        '--include-archived',
        action='store_true',
        help='Include archived threads in migration. Default is active threads only.',
    )
    args = parser.parse_args()

    thread_ids = [parse_thread_id(value) for value in args.thread + args.deeplink]
    thread_ids = list(dict.fromkeys(thread_ids))
    codex_home = Path(args.codex_home).expanduser().resolve()
    db_path = codex_home / 'state_5.sqlite'

    if not db_path.exists():
        raise FileNotFoundError(f'State DB not found: {db_path}')

    bulk_mode = bool(args.from_path or args.from_name or args.to)
    if bulk_mode:
        if not args.to:
            raise ValueError('Bulk mode requires --to.')
        if bool(args.from_path) == bool(args.from_name):
            raise ValueError('Bulk mode requires exactly one of --from or --from-name.')
        target_cwd = normalized_path(args.to)
    else:
        if not args.project:
            raise ValueError('Provide --project when not using bulk mode.')
        if not thread_ids:
            raise ValueError('Provide at least one --thread or --deeplink.')
        target_cwd = normalized_path(args.project)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        if bulk_mode:
            if args.from_path:
                source_rows = fetch_rows_by_old_cwd(cur, normalized_path(args.from_path), args.include_archived)
            else:
                source_rows = fetch_rows_by_old_folder_name(cur, args.from_name.strip(), args.include_archived)
            if not source_rows:
                raise RuntimeError(
                    'No threads matched the provided source filter. '
                    'By default only active threads are included; use --include-archived if needed.'
                )

            if thread_ids:
                selected_ids = set(thread_ids)
                rows = [row for row in source_rows if row['id'] in selected_ids]
                missing = selected_ids - {row['id'] for row in rows}
                if missing:
                    raise RuntimeError(
                        'Some specified thread IDs are not in the selected source set: '
                        + ', '.join(sorted(missing))
                    )
            else:
                rows = source_rows
        else:
            rows = fetch_thread_rows(cur, thread_ids, args.include_archived)
    finally:
        conn.close()

    print(f'db_path={db_path}')
    print(f'mode={"bulk" if bulk_mode else "explicit"}')
    print(f'include_archived={str(args.include_archived).lower()}')
    print(f'threads_count={len(rows)}')
    print(f'new_cwd={target_cwd}')
    for row in rows:
        print(
            f'thread={row["id"]} archived={str(row["archived"]).lower()} '
            f'old_cwd={row["old_cwd"]} rollout_path={row["rollout_path"]}'
        )

    if args.dry_run:
        print('dry_run=true')
        return 0

    backup_map: dict[str, dict] = {}
    db_updated = False
    try:
        for row in rows:
            rollout_path = Path(row['rollout_path']).expanduser()
            backup_map[row['id']] = {
                'path': rollout_path,
                'backup': update_rollout_session_meta_cwd(rollout_path, row['id'], target_cwd),
            }

        update_db_cwd_bulk(db_path, rows, target_cwd)
        db_updated = True
        verify(db_path, rows, target_cwd)
    except Exception as original_error:
        rollback_errors: list[str] = []
        try:
            restore_rollout_files(backup_map)
        except Exception as rollback_file_error:  # pragma: no cover
            rollback_errors.append(f'rollout restore failed: {rollback_file_error}')

        if db_updated:
            try:
                restore_db_old_cwds(db_path, rows)
            except Exception as rollback_db_error:  # pragma: no cover
                rollback_errors.append(f'db restore failed: {rollback_db_error}')

        if rollback_errors:
            raise RuntimeError(
                f'Migration failed: {original_error}. Rollback issues: {"; ".join(rollback_errors)}'
            ) from original_error
        raise

    for thread_id, record in backup_map.items():
        print(f'backup_thread={thread_id} backup_path={record["backup"]}')
    print('status=ok')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'error={exc}', file=sys.stderr)
        raise
