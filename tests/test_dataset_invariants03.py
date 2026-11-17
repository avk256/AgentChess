"""Dataset integrity for 0.2.1 through 0.5.4; expansion must not invalidate older tests."""
import json
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_import_report_consistency():
    path=ROOT/'data'/'converted'/'import_summary.json'
    if not path.exists(): return
    data=json.loads(path.read_text(encoding='utf8'))
    totals=data['database_totals']
    assert totals['sources']==33
    assert totals['games']==18805
    assert totals['chapters']==437
    assert sum(data['record_statuses'].values())==totals['games']
    assert data['record_statuses'].get('PARSE_ERROR',0)==0

def test_database_candidates_are_not_implicitly_ready():
    db=ROOT/'data'/'agentchess.sqlite3'
    if not db.exists(): return
    c=sqlite3.connect(db)
    try:
        all_rows=c.execute('SELECT COUNT(*) FROM cdb_records').fetchone()[0]
        assert all_rows==18805
        candidates=c.execute('SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
        # MVP 0.3 started with 7,851 candidates. MVP 0.5 adds up to
        # 6,492 more source-based exercises; both stages and partial
        # non-destructive expansion are acceptable here.
        assert 7851 <= candidates <= all_rows
        # Every exercise must refer to a real imported record.
        orphans=c.execute('''SELECT COUNT(*) FROM cdb_exercises e
            LEFT JOIN cdb_records r ON r.id=e.record_id
            WHERE r.id IS NULL''').fetchone()[0]
        assert orphans==0
        # We create at most one exercise per CDB record.
        duplicates=c.execute('''SELECT COUNT(*) FROM (
            SELECT record_id FROM cdb_exercises
            GROUP BY record_id HAVING COUNT(*)>1)''').fetchone()[0]
        assert duplicates==0
    finally: c.close()
