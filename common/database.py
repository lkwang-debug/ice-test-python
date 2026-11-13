"""SELECT-only database oracles. No test-data INSERT/UPDATE/DELETE facilities."""
import base64
import csv
import io
import json
import math
import os
import re
from pathlib import Path


def validate_select(sql):
    if not isinstance(sql, str) or not re.match(r"^\s*SELECT\b", sql, re.I):
        raise ValueError("Database verification allows SELECT only")
    if re.search(r";|--|/\*|\*/|\b(INTO|OUTFILE|DUMPFILE|FOR\s+UPDATE|LOCK|SLEEP|BENCHMARK)\b", sql, re.I):
        raise ValueError("Unsafe SELECT for read-only verification")


def bind_select(sql, params, dialect="mysql"):
    validate_select(sql)
    if sql.count("%s") != len(params):
        raise ValueError("SQL placeholder count mismatch")
    def literal(v):
        if v is None:
            return "NULL"
        if type(v) is bool:
            return "1" if v else "0"
        if type(v) in (int, float):
            if not math.isfinite(v):
                raise ValueError("Invalid numeric SQL value")
            return str(v)
        if not isinstance(v, str):
            raise ValueError("SQL parameters must be scalar")
        if dialect == "kingbase":
            # The SSH client enforces standard_conforming_strings=on before
            # execution, so doubling quotes keeps backslashes literal too.
            if "\x00" in v:
                raise ValueError("Kingbase text parameters cannot contain NUL")
            return "'" + v.replace("'", "''") + "'"
        # Hex literals avoid shell/SQL quoting and NO_BACKSLASH_ESCAPES ambiguity.
        return "CONVERT(0x%s USING utf8mb4)" % v.encode("utf-8").hex() if v else "''"
    parts = sql.split("%s")
    return "".join(part + (literal(params[i]) if i < len(params) else "") for i, part in enumerate(parts))


def decode_csv_rows(text, null_marker):
    """Keep SQL NULL distinct from empty strings, including multiline fields."""
    reader = csv.reader(io.StringIO(text))
    headers = next(reader, None)
    if headers is None:
        return []
    rows = []
    for values in reader:
        # ksql emits a single empty-string field as a blank CSV record. A
        # DictReader silently skips it, confusing one empty value with no row.
        if not values and len(headers) == 1:
            values = [""]
        if len(values) != len(headers):
            raise ValueError("Database CSV column count differs from its header")
        rows.append({key: None if value == null_marker else value for key, value in zip(headers, values)})
    return rows


class ReadonlyDatabase:
    def __init__(self, config):
        self.config = config or {}
        self._ssh_client = None
        self._resolved = self.config.get("_resolved")

    def close(self):
        if self._ssh_client is not None:
            self._ssh_client.close()
            self._ssh_client = None

    @property
    def schema_expression(self):
        """Metadata schema differs from database name on Kingbase."""
        return "current_schema()" if self.dialect == "kingbase" else "DATABASE()"

    def fetch(self, sql, params=()):
        validate_select(sql)
        if not self.config:
            raise RuntimeError("Database oracle declared but database is not configured")
        backend = self.config.get("backend", "mysql")
        if backend not in {"auto", "mysql", "ssh_mysql", "ssh_kingbase"}:
            raise RuntimeError("Unsupported database backend: " + str(backend))
        if backend in {"auto", "ssh_mysql", "ssh_kingbase"}:
            self.resolve()
            return self._ssh_fetch(bind_select(sql, params, self.dialect))
        import pymysql
        cfg = self.config
        password = os.environ.get(cfg.get("password_env", "ICE_DB_PASSWORD"), cfg.get("password"))
        if password is None:
            raise RuntimeError("Missing database password environment variable")
        with pymysql.connect(host=cfg["host"], port=cfg.get("port", 3306), user=cfg["user"],
                             password=password, database=cfg["name"], charset="utf8mb4",
                             connect_timeout=10, read_timeout=10,
                             cursorclass=pymysql.cursors.DictCursor) as conn:
            with conn.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                try:
                    cursor.execute(sql, params)
                    return cursor.fetchall()
                finally:
                    conn.rollback()

    @property
    def dialect(self):
        backend = self.config.get("backend", "mysql")
        if backend == "auto":
            backend = self.resolve()["backend"]
        return "kingbase" if backend == "ssh_kingbase" else "mysql"

    def resolve(self):
        if self._resolved is None:
            if self.config.get("backend", "mysql") not in {"auto", "ssh_mysql", "ssh_kingbase"}:
                self._resolved = {"backend": "mysql"}
            else:
                fields = {k: v for k, v in self.config.items() if k in
                          {"backend", "config_dir", "server_config", "container", "client", "library_path"}}
                self._resolved = self._remote({"operation": "resolve", "config": fields})
        return self._resolved

    def description(self):
        selected = self.resolve()
        if "source" not in selected:
            return {"backend": selected["backend"], "host": self.config.get("host")}
        return {"backend": selected["backend"], "config_files": selected["source"]["config_files"],
                "profiles": selected["source"]["profiles"], "target": selected["target"],
                "container": selected["client"]["container"], "client": selected["client"]["client"]}

    def epoch_expression(self, column):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", column):
            raise ValueError("Invalid timestamp column")
        if self.dialect == "kingbase":
            # Route timestamps are local timestamps, while CURRENT_TIMESTAMP has a zone.
            return "FLOOR(EXTRACT(EPOCH FROM CAST(%s AS TIMESTAMP)))" % column
        return "UNIX_TIMESTAMP(%s)" % column

    def text_column_length(self, table, column):
        if self.dialect == "kingbase":
            return self.fetch("SELECT (a.atttypmod-4) AS max_length FROM pg_attribute a "
                              "JOIN pg_class c ON a.attrelid=c.oid JOIN pg_namespace n ON c.relnamespace=n.oid "
                              "JOIN pg_type t ON a.atttypid=t.oid WHERE lower(c.relname)=lower(%s) "
                              "AND lower(a.attname)=lower(%s) AND n.nspname=current_schema() "
                              "AND t.typname IN ('varchar','bpchar') AND a.atttypmod>4", [table, column])
        return self.fetch("SELECT CHARACTER_MAXIMUM_LENGTH AS max_length FROM information_schema.COLUMNS "
                          "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s", [table, column])

    def room_log_tables(self):
        if self.dialect == "kingbase":
            return self.fetch("SELECT tablename AS table_name FROM pg_tables WHERE schemaname=current_schema() AND tablename LIKE 't_roomlog%'")
        return self.fetch("SELECT TABLE_NAME AS table_name FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 't_roomlog%'")

    def table_columns(self, table):
        rows = self.fetch("SELECT column_name AS column_name FROM information_schema.columns WHERE table_schema="
                          + self.schema_expression + " AND lower(table_name)=lower(%s)", [table])
        return {row["column_name"].lower() for row in rows}

    def _remote(self, request):
        import paramiko
        cfg = self.config
        password = os.environ.get(cfg.get("password_env", "ICE_SSH_PASSWORD"), cfg.get("password"))
        if password is None:
            raise RuntimeError("Missing SSH password for database oracle")
        client = self._ssh_client
        if client is None or client.get_transport() is None or not client.get_transport().is_active():
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(cfg["host"], port=cfg.get("ssh_port", 22), username=cfg.get("user", "root"),
                           password=password, timeout=10, auth_timeout=10)
            self._ssh_client = client
        payload = base64.b64encode(json.dumps(request).encode()).decode()
        script = Path(__file__).with_name("database_remote.py").read_text(encoding="utf-8")
        script += "\nimport base64\nprint(json.dumps(main(json.loads(base64.b64decode(" + repr(payload) + ")))))\n"
        try:
            stdin, stdout, stderr = client.exec_command("python3 -", timeout=45)
            stdin.write(script)
            stdin.channel.shutdown_write()
            output, error = stdout.read().decode(), stderr.read().decode()
            if stdout.channel.recv_exit_status():
                # Import/transport errors only; query failures are returned without traceback.
                raise RuntimeError("SSH database helper failed: " + error[-800:])
            response = json.loads(output)
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]
        except Exception:
            self.close()
            raise

    def _ssh_fetch(self, sql):
        return self._remote({"operation": "fetch", "resolved": self.resolve(), "sql": sql})


def db_text(value):
    """CLI and DB-API serialize numbers differently; compare DB state canonically."""
    return None if value is None else str(value)
