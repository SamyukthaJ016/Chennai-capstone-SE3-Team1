from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
SEED_DIR = REPO_ROOT / "seed"
ENV_FILE = REPO_ROOT / ".env"

DEFAULTS = {
    "host": "localhost",
    "port": "5432",
    "dbname": "trading_platform",
    "user": "postgres",
    "password": "postgres",
}

ENV_KEYS = {
    "host": "PGHOST",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
}

_WINDOWS_PSQL_GLOBS = [
    "C:\\Program Files\\PostgreSQL\\*\\bin\\psql.exe",
    "C:\\Program Files (x86)\\PostgreSQL\\*\\bin\\psql.exe",
]

FIELD_SEP = "\x1f"


class DbError(RuntimeError):
    pass


def _read_env_file():
    values = {}
    if not ENV_FILE.is_file():
        return values
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip().upper()] = val.strip().strip('"').strip("'")
    return values


def find_psql():
    override = os.environ.get("PSQL_BIN")
    if override:
        if Path(override).is_file():
            return override
        raise DbError("PSQL_BIN is set to " + repr(override) + " but that file does not exist.")

    on_path = shutil.which("psql")
    if on_path:
        return on_path

    if sys.platform == "win32":
        import glob

        found = []
        for pattern in _WINDOWS_PSQL_GLOBS:
            found.extend(glob.glob(pattern))
        if found:
            return sorted(found)[-1]

    raise DbError(
        "psql was not found. Install the PostgreSQL client tools, or point at the "
        "binary directly with PSQL_BIN=/path/to/psql."
    )


@dataclass
class DbConfig:
    host: str
    port: str
    dbname: str
    user: str
    password: str
    psql: str

    @classmethod
    def resolve(cls, args=None):
        dotenv = _read_env_file()
        settings = {}
        for name, env_key in ENV_KEYS.items():
            cli_value = getattr(args, name, None) if args is not None else None
            settings[name] = (
                cli_value
                or os.environ.get(env_key)
                or dotenv.get(env_key)
                or DEFAULTS[name]
            )
        psql = getattr(args, "psql", None) if args is not None else None
        return cls(psql=psql or dotenv.get("PSQL_BIN") or find_psql(), **settings)


    def _env(self):
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password
        env["PGCLIENTENCODING"] = "UTF8"
        return env

    def _base_cmd(self, dbname=None):
        return [
            self.psql,
            "--no-psqlrc",
            "--host", self.host,
            "--port", str(self.port),
            "--username", self.user,
            "--dbname", dbname or self.dbname,
            "--set", "ON_ERROR_STOP=1",
        ]

    def run(self, sql=None, file=None, script=None, dbname=None, quiet=True,
            verbose_errors=False, tuples_only=False):
        sources = [s is not None for s in (sql, file, script)]
        if sum(sources) != 1:
            raise ValueError("pass exactly one of sql=, file= or script=")

        cmd = self._base_cmd(dbname)
        if quiet:
            cmd.append("--quiet")
        if tuples_only:
            cmd += ["--tuples-only", "--no-align"]
        if verbose_errors:
            cmd += ["--set", "VERBOSITY=verbose"]

        stdin_text = None
        if file is not None:
            cmd += ["--file", str(file)]
        elif script is not None:
            cmd += ["--file", "-"]
            stdin_text = script
        else:
            cmd += ["--command", sql]

        return subprocess.run(
            cmd, env=self._env(), input=stdin_text, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    def run_or_die(self, what, **kwargs):
        proc = self.run(**kwargs)
        if proc.returncode != 0:
            raise DbError(
                what + " failed (psql exit " + str(proc.returncode) + ").\n"
                + (proc.stderr or proc.stdout).strip()
            )
        return proc.stdout

    def scalar(self, sql, dbname=None):
        cmd = self._base_cmd(dbname) + ["--tuples-only", "--no-align", "--command", sql]
        proc = subprocess.run(
            cmd, env=self._env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise DbError("query failed: " + sql + "\n" + (proc.stderr or proc.stdout).strip())
        return proc.stdout.strip()

    def rows(self, sql, dbname=None):
        cmd = self._base_cmd(dbname) + [
            "--tuples-only", "--no-align", "--field-separator", FIELD_SEP, "--command", sql,
        ]
        proc = subprocess.run(
            cmd, env=self._env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise DbError("query failed: " + sql + "\n" + (proc.stderr or proc.stdout).strip())
        return [line.split(FIELD_SEP) for line in proc.stdout.splitlines() if line.strip()]

    def server_reachable(self):
        proc = self.run(sql="SELECT 1", dbname="postgres")
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def database_exists(self):
        out = self.scalar(
            "SELECT 1 FROM pg_database WHERE datname = " + quote_literal(self.dbname),
            dbname="postgres",
        )
        return out == "1"

    def describe(self):
        return self.user + "@" + self.host + ":" + str(self.port) + "/" + self.dbname


def quote_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def add_connection_args(parser):
    g = parser.add_argument_group("connection (env vars and .env also work)")
    g.add_argument("--host", help="database host (default " + DEFAULTS["host"] + ", or $PGHOST)")
    g.add_argument("--port", help="database port (default " + DEFAULTS["port"] + ", or $PGPORT)")
    g.add_argument("--dbname", help="database name (default " + DEFAULTS["dbname"] + ", or $PGDATABASE)")
    g.add_argument("--user", help="database user (default " + DEFAULTS["user"] + ", or $PGUSER)")
    g.add_argument("--password", help="database password (default 'postgres', or $PGPASSWORD)")
    g.add_argument("--psql", help="path to the psql binary (default: found on PATH, or $PSQL_BIN)")
