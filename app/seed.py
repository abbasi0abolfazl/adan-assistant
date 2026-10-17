import os
import sqlite3
from contextlib import closing
from pathlib import Path
from .errors import AppError


def seed_database(data_dir: Path, db_path: Path) -> None:
    """Create once; never overwrite an existing DB or silently repair user data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        try:
            with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
                version = conn.execute('PRAGMA user_version').fetchone()[0]
                ok = conn.execute('PRAGMA quick_check').fetchone()[0]
                tables = {x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if version != 1 or ok != 'ok' or not {'customers','products','orders','order_items'} <= tables:
                    raise ValueError('Sample database version or integrity mismatch')
        except (sqlite3.Error, ValueError) as exc:
            raise AppError('DATABASE_INVALID', 'Existing database is incompatible; back it up before rebuilding.', 503) from exc
        return
    temporary = db_path.with_suffix(f'.{os.getpid()}.tmp')
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript((data_dir / 'db/schema.sql').read_text())
            connection.executescript('BEGIN;\n' + (data_dir / 'db/seed.sql').read_text() + '\nCOMMIT;')
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Invalid seed foreign keys')
        finally:
            connection.close()
        os.replace(temporary, db_path)
    finally:
        temporary.unlink(missing_ok=True)
