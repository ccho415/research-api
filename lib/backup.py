"""pg_dump behind an HTTP endpoint.

n8n cannot produce a dump on its own - its Postgres node only runs queries -
so the dump is made here and handed back as a file for n8n to upload.

The dump is written to a temp file rather than streamed straight out of
pg_dump: on a 2GB box the whole point is to never hold the database in
memory, and a file also lets the caller see the size before deciding whether
to trust it.
"""

import os
import re
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


def pg_env():
    """Connection settings as PG* variables rather than argv.

    A connection URI on the command line puts the password in the process
    list; the PG* variables do the same job without that.

    Either form of configuration works: DATABASE_URL, or the PG* variables
    set directly.  The split form is there because a URL has to
    percent-encode the password, and a password pasted into a URL by hand is
    the classic failure that reports itself only as "authentication failed".
    """
    env = dict(os.environ)
    url = database_url()
    if url:
        u = urllib.parse.urlsplit(url)
        from_url = {"PGHOST": u.hostname or "",
                    "PGPORT": str(u.port or 5432),
                    "PGUSER": urllib.parse.unquote(u.username or ""),
                    "PGDATABASE": (u.path or "/").lstrip("/") or "postgres"}
        if u.password:
            from_url["PGPASSWORD"] = urllib.parse.unquote(u.password)
        for key, value in from_url.items():
            # An explicitly set PG* variable wins over the URL.  Zeabur
            # injects a connection string of its own pointing at the
            # platform's default database, and letting that beat a
            # deliberate PGDATABASE is how you end up dumping the wrong
            # database every night without noticing.
            if not os.environ.get(key):
                env[key] = value

    env.setdefault("PGPORT", "5432")
    env.setdefault("PGCONNECT_TIMEOUT", "15")
    missing = [k for k in ("PGHOST", "PGUSER", "PGDATABASE") if not env.get(k)]
    if missing:
        raise RuntimeError("database is not configured: set DATABASE_URL, "
                           f"or set {', '.join(missing)}")
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
    sql = ("SELECT COALESCE(SUM(GREATEST(c.reltuples, 0))::bigint, 0) "
           "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
           "WHERE c.relkind = 'r' AND n.nspname = 'public'")
    try:
        return int(_run(["psql", "-At", "-c", sql], pg_env(), 60))
    except Exception:
        # Never let the sanity check be the reason a backup fails.
        return None


def config_report():
    """What the process actually sees, and where each setting came from.

    "password authentication failed" cannot tell you whether the password is
    wrong or whether a variable you deleted is still in the container from
    before the last restart.  This answers that without printing the secret.
    """
    url = database_url()
    report = {
        "connection_url_present": bool(url),
        "connection_url_variable": next(
            (n for n in ("DATABASE_URL", "POSTGRES_CONNECTION_STRING")
             if os.environ.get(n, "").strip()), None),
        "explicitly_set": sorted(
            k for k in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")
            if os.environ.get(k)),
    }
    try:
        env = pg_env()
    except RuntimeError as e:
        report["resolved"] = None
        report["error"] = str(e)
        return report

    password = env.get("PGPASSWORD", "")
    report["resolved"] = {
        "host": env["PGHOST"], "port": env["PGPORT"],
        "user": env["PGUSER"], "database": env["PGDATABASE"],
        # Never the value.  The length and whether it still looks like an
        # unresolved ${...} reference is enough to identify the usual faults.
        "password_length": len(password),
        "password_looks_like_unresolved_reference":
            password.startswith("${") and password.endswith("}"),
    }
    report["optional_settings"] = optional_settings()
    report["build"] = build_marker()
    return report


# Settings that change how well the service behaves rather than whether it runs,
# so nothing fails when they are missing and nobody notices they are missing.
# ACADEMIC_MAILTO is a personal address and NCBI_API_KEY is a secret, so this
# reports whether each is set and never what it is.
OPTIONAL = ("ACADEMIC_MAILTO", "NCBI_API_KEY", "SEMANTIC_SCHOLAR_API_KEY")


def optional_settings():
    return {k: bool(os.environ.get(k, "").strip()) for k in OPTIONAL}


def build_marker():
    """Which build is answering, so far as the container can tell.

    Asking whether a deploy has landed has meant guessing at wall-clock times
    all day. The platform injects its own build metadata under its own prefix;
    the names are reported so a follow-up can read the useful one, and any value
    that is clearly a commit hash is reported outright because a commit hash is
    not a secret and is the single most useful fact here.
    """
    names = sorted(k for k in os.environ if k.startswith(("ZEABUR", "RAILWAY", "GIT")))
    commit = None
    for k in names:
        v = os.environ.get(k, "").strip()
        if re.fullmatch(r"[0-9a-f]{7,40}", v):
            commit = {"variable": k, "value": v}
            break
    return {"platform_variables": names, "commit": commit}


def stats():
    """Cheap facts about the database, for deciding whether to bother dumping.

    Read before the dump rather than after: if the database has gone empty
    there is no point spending the memory, and the alert should say so.
    """
    env = pg_env()
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
    env = pg_env()
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


DRILL_PREFIX = "restore_drill_"


def restore_drill(dump_path):
    """Restore a dump into a throwaway database and report what came back.

    This is the only check on a backup that means anything.  pg_dump exiting
    zero says the file was written, not that it can be read back, and the
    difference only shows up on the day you need it.

    The scratch database is created and dropped here; the real database is
    never a restore target, so a drill cannot damage anything.
    """
    env = pg_env()
    source = stats()
    target = DRILL_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    # CREATE DATABASE has to be issued from some other database, so talk to
    # the server's default one for the create and the drop.
    admin = dict(env, PGDATABASE="postgres")
    _run(["createdb", target], admin, 60)
    try:
        into = dict(env, PGDATABASE=target)
        restore = subprocess.run(
            ["pg_restore", "--no-owner", "--no-privileges", "--dbname", target,
             dump_path],
            env=into, capture_output=True, timeout=DUMP_TIMEOUT)
        # pg_restore warns about things like missing roles even on a clean
        # run, so the exit code alone decides failure and the text is carried
        # through for reading.
        notices = restore.stderr.decode("utf-8", "replace").strip()

        # reltuples is zero until the planner has looked at the new tables.
        _run(["psql", "-At", "-c", "ANALYZE"], into, 300)
        got = _run(["psql", "-At", "-c",
                    "SELECT (SELECT count(*) FROM information_schema.tables "
                    "        WHERE table_schema = 'public') || '|' || "
                    "       COALESCE((SELECT SUM(GREATEST(c.reltuples, 0))::bigint "
                    "        FROM pg_class c JOIN pg_namespace n "
                    "          ON n.oid = c.relnamespace "
                    "        WHERE c.relkind = 'r' AND n.nspname = 'public'), 0)"],
                   into, 120)
        tables, rows = (int(x) for x in got.split("|"))
    finally:
        # Drop even if the restore blew up, or the scratch databases pile up.
        try:
            _run(["dropdb", "--if-exists", target], admin, 60)
            dropped = True
        except Exception:
            dropped = False

    return {
        "scratch_database": target,
        "dropped_afterwards": dropped,
        "restore_exit_code": restore.returncode,
        "source": {"database": source["database"], "n_tables": source["n_tables"],
                   "row_estimate": source["row_estimate"]},
        "restored": {"n_tables": tables, "row_estimate": rows},
        "tables_match": tables == source["n_tables"],
        "ok": restore.returncode == 0 and tables == source["n_tables"],
        "pg_restore_output": notices[:2000],
    }
