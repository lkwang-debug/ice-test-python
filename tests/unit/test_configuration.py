"""Single-file configuration stays consistent across source and relocated packages."""
import ast
import runpy
from pathlib import Path

from common import config
from common.runtime import load_profile


def test_changing_one_server_address_updates_all_endpoints_in_relocated_package(tmp_path):
    source = Path(config.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    host_assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "SERVER_HOST" for t in node.targets))
    lines = source.splitlines(keepends=True)
    lines[host_assignment.lineno - 1] = 'SERVER_HOST = "192.0.2.17"\n'
    package = tmp_path / "unpacked" / "common"
    package.mkdir(parents=True)
    path = package / "config.py"
    path.write_text("".join(lines), encoding="utf-8")
    cfg = runpy.run_path(str(path))
    assert cfg["TEST_CONFIG"]["host"] == cfg["TEST_CONFIG"]["database"]["host"] == "192.0.2.17"
    assert cfg["ICE_CONFIG"]["locator"] == "IceGrid/Locator:tcp -h 192.0.2.17 -p 22000"
    assert Path(cfg["EXCEL_CONFIG"]["file_path"]) == tmp_path / "unpacked/data/test_cases.xlsx"
    assert Path(cfg["ALLURE_CONFIG"]["output_dir"]) == tmp_path / "unpacked/allure_report"


def test_host_override_keeps_default_ssh_oracle_on_same_server():
    profile = load_profile(host="192.0.2.18")
    assert profile["host"] == profile["database"]["host"] == "192.0.2.18"
    assert config.TEST_CONFIG["host"] == config.SERVER_HOST  # Loading a profile cannot mutate the source.


def test_explicit_separate_database_in_legacy_profile_is_preserved(tmp_path):
    import json
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"host": "192.0.2.19", "database": {
        "backend": "ssh_mysql", "host": "192.0.2.20"}}), encoding="utf-8")
    profile = load_profile(path)
    assert profile["host"] == "192.0.2.19" and profile["database"]["host"] == "192.0.2.20"


def test_kingbase_parameters_cannot_become_sql():
    from common.database import bind_select
    import sqlite3
    # SQLite provides an independent parser with the same standard literal
    # quoting rule, so test actual evaluation instead of mirroring escaping.
    value = "测试'\\;DELETE FROM input;"
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE input(value TEXT)")
        db.execute("INSERT INTO input VALUES (?)", [value])
        sql = bind_select("SELECT value FROM input WHERE value=%s", [value], "kingbase")
        assert db.execute(sql).fetchall() == [(value,)]


def test_kingbase_csv_preserves_null_empty_unicode_and_multiline_values():
    from common.database import decode_csv_rows
    value = 'id,name,empty,missing\n1,"测试,用户\n第二行",,__NULL__\n'
    assert decode_csv_rows(value, "__NULL__") == [
        {"id": "1", "name": "测试,用户\n第二行", "empty": "", "missing": None}]


def test_kingbase_single_empty_value_is_a_row_and_not_an_empty_result():
    from common.database import decode_csv_rows
    assert decode_csv_rows("ParentID\n\n", "__NULL__") == [{"ParentID": ""}]
    assert decode_csv_rows("ParentID\n", "__NULL__") == []
    assert decode_csv_rows("ParentID\n__NULL__\n", "__NULL__") == [{"ParentID": None}]
    assert decode_csv_rows("ParentID\n\n\n", "__NULL__") == [{"ParentID": ""}, {"ParentID": ""}]
