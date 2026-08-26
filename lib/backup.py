"""pg_dump behind an HTTP endpoint.

n8n cannot produce a dump on its own - its Postgres node only runs queries -
so the dump is made here and handed back as a file for n8n to upload.

The dump is written to a temp file rather than streamed straight out of
pg_dump: on a 2GB box the whole point is to never hold the database in
memory, and a file also lets the caller see the size before deciding whether
to trust it.
"""

import os
import subprocess
import tempfile
import threading
import urllib.parse
from datetime import datetime, timezone

DUMP_TIMEOUT = 900

# One dump at a time.  Two concurrent pg_dumps on a 2GB instance is the
# fastest way to OOM the whole project.
_lock = threading.Lock()


def acquire():
    return _lock.acquire(blocking=False)


def release():
    if _lock.locked():
        _lock.release()


def database_url():
    for name in ("DATABASE_URL", "POSTGRES_CONNECTION_STRING"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _pg_env(url):
    """Connection settings as PG* variables rather than argv.

    A connection URI on the command line puts the password in the process
    list; the PG* variables do the same job without that.
    """
    u = urllib.parse.urlsplit(url)
    env = dict(os.environ)
    env["PGHOST"] = u.hostname or ""
    env["PGPORT"] = str(u.port or 5432)
    env["PGUSER"] = urllib.parse.unquote(u.username or "")
    env["PGDATABASE"] = (u.path or "/").lstrip("/") or "postgres"
    if u.password:
        env["PGPASSWORD"] = urllib.parse.unquote(u.password)
    env.setdefault("PGCONNECT_TIMEOUT", "15")
    return env


def _run(cmd, env, timeout):
    p = subprocess.run(cmd, env=env, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(err[:500] or f"{cmd[0]} exited {p.returncode}")
    return p.stdout.decode("utf-8", "replace").strip()


def row_total():
    """Live row estimate across the public schema.

    A dump that runs cleanly against an empty database is still a successful
    backup of nothing, and that is the failure people discover a year later.
    Recording this next to the byte count makes the silent case visible.

    These are planner estimates from pg_class, not exact counts - accurate
    enough to notice that a number collapsed, and it does not scan the tables.
    """
    url = database_url()
    if not url:
        return None
    sql = ("SELECT COALESCE(SUM(GREATEST(c.reltuples, 0))::bigint, 0) "
           "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
           "WHERE c.relkind = 'r' AND n.nspname = 'public'")
    try:
        return int(_run(["psql", "-At", "-c", sql], _pg_env(url), 60))
    except Exception:
        # Never let the sanity check be the reason a backup fails.
        return None


def stats():
    """Cheap facts about the database, for deciding whether to bother dumping.

    Read before the dump rather than after: if the database has gone empty
    there is no point spending the memory, and the alert should say so.
    """
    url = database_url()
    if not url:
        raise RuntimeError("neither DATABASE_URL nor POSTGRES_CONNECTION_STRING is set")
    env = _pg_env(url)
    sql = ("SELECT (SELECT count(*) FROM information_schema.tables "
           "        WHERE table_schema = 'public') || '|' || "
           "       COALESCE((SELECT SUM(GREATEST(c.reltuples, 0))::bigint "
           "        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
           "        WHERE c.relkind = 'r' AND n.nspname = 'public'), 0) || '|' || "
           "       pg_database_size(current_database()) || '|' || "
           "       current_setting('server_version')")
    tables, rows, size, version = _run(["psql", "-At", "-c", sql], env, 60).split("|")
    return {"database": env["PGDATABASE"], "server_version": version,
            "n_tables": int(tables), "row_estimate": int(rows),
            "db_size_bytes": int(size)}


def dump():
    """Write a custom-format dump and return (path, filename, bytes).

    Custom format so restoring is `pg_restore`, which verifies the archive
    header and refuses a truncated file.  A plain SQL dump would happily
    replay half a backup and leave you thinking it worked.
    """
    url = database_url()
    if not url:
        raise RuntimeError("neither DATABASE_URL nor POSTGRES_CONNECTION_STRING is set")

    env = _pg_env(url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{env['PGDATABASE']}-{stamp}.dump"

    fd, path = tempfile.mkstemp(prefix="pgdump-", suffix=".dump")
    os.close(fd)
    try:
        _run(["pg_dump", "--format=custom", "--compress=9",
              "--no-owner", "--no-privileges", "--file", path],
             env, DUMP_TIMEOUT)
    except Exception:
        os.unlink(path)
        raise

    size = os.path.getsize(path)
    if size == 0:
        os.unlink(path)
        raise RuntimeError("pg_dump produced an empty file")
    return path, name, size
