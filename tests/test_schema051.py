"""Regression tests: legacy fixture schema, repeatability, preservation."""
import importlib.util
import sqlite3
from pathlib import Path

module_file = Path(__file__).resolve().parents[1] / 'backend' / 'schema051.py'
spec = importlib.util.spec_from_file_location('schema051', module_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ensure_tree_json_column = module.ensure_tree_json_column


def test_legacy_record_schema_migrates_without_loss(tmp_path):
    db = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE cdb_records(id INTEGER PRIMARY KEY, mainline_json TEXT)')
        c.execute('INSERT INTO cdb_records VALUES(7, ?)', ('["e2e4"]',))
    assert ensure_tree_json_column(db) is True
    assert ensure_tree_json_column(db) is False
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT id,mainline_json,tree_json FROM cdb_records').fetchall() == [(7, '["e2e4"]', None)]


def test_real_style_tree_preserved(tmp_path):
    db = tmp_path / 'current.sqlite3'
    original = '{"variations":[{"uci":"e2e4","children":[]}]}'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,mainline_json TEXT,tree_json TEXT)')
        c.execute('INSERT INTO cdb_records VALUES(1,?,?)', ('["e2e4"]', original))
    assert ensure_tree_json_column(db) is False
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT tree_json FROM cdb_records WHERE id=1').fetchone()[0] == original


def test_missing_records_table_fails_clearly(tmp_path):
    db = tmp_path / 'empty.sqlite3'
    try:
        ensure_tree_json_column(db)
    except RuntimeError as exc:
        assert 'cdb_records' in str(exc)
    else:
        raise AssertionError('Missing table must fail clearly')
