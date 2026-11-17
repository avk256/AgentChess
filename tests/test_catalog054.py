"""MVP 0.5.4 checks for schema and catalog consistency without network or Stockfish."""
import sqlite3
from pathlib import Path


def _counts(db_path):
    with sqlite3.connect(db_path) as con:
        n_records=con.execute('SELECT COUNT(*) FROM cdb_records').fetchone()[0]
        n_exercises=con.execute('SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
        bad=con.execute('''SELECT COUNT(*) FROM cdb_exercises e
            LEFT JOIN cdb_records r ON r.id=e.record_id
            WHERE r.id IS NULL''').fetchone()[0]
        dup=con.execute('''SELECT COUNT(*) FROM (
            SELECT record_id FROM cdb_exercises GROUP BY record_id
            HAVING COUNT(*)>1)''').fetchone()[0]
    return n_records,n_exercises,bad,dup


def _synthetic_catalog(tmp_path, exercise_count):
    path=tmp_path/'catalog.sqlite3'
    with sqlite3.connect(path) as con:
        con.executescript('''CREATE TABLE cdb_records (id INTEGER PRIMARY KEY);
        CREATE TABLE cdb_exercises (id INTEGER PRIMARY KEY, record_id INTEGER);
        WITH RECURSIVE t(n) AS (
            SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<18805
        ) INSERT INTO cdb_records (id) SELECT n FROM t;
        ''')
        con.executemany('INSERT INTO cdb_exercises (record_id) VALUES (?)',
                        ((i,) for i in range(1,exercise_count+1)))
    return path


def test_legacy_catalog_counts_are_consistent(tmp_path):
    assert _counts(_synthetic_catalog(tmp_path,7851)) == (18805,7851,0,0)


def test_expanded_catalog_counts_are_consistent(tmp_path):
    assert _counts(_synthetic_catalog(tmp_path,14343)) == (18805,14343,0,0)


def test_duplicate_exercise_is_detected(tmp_path):
    path=_synthetic_catalog(tmp_path,7851)
    with sqlite3.connect(path) as con:
        con.execute('INSERT INTO cdb_exercises (record_id) VALUES (1)')
    assert _counts(path)[3] == 1
