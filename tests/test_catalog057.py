"""Regression: topics added after CDB import remain searchable in catalog."""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from catalog import exercise_catalog_query


def test_catalog_uses_exercise_topic_and_paginates(tmp_path):
    db = tmp_path / 'catalog.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''
          CREATE TABLE cdb_sources (id INTEGER PRIMARY KEY, filename TEXT);
          CREATE TABLE cdb_records (id INTEGER PRIMARY KEY, source_id INTEGER,
              original_id INTEGER, event TEXT, normalized_fen TEXT,
              record_type TEXT, topic TEXT, elo INTEGER, status TEXT);
          CREATE TABLE cdb_exercises (id INTEGER PRIMARY KEY, record_id INTEGER,
              topic TEXT, mate_in INTEGER, difficulty INTEGER);
        ''')
        c.execute("INSERT INTO cdb_sources VALUES (1,'School2.ru.cdb')")
        for i in range(1,4):
            c.execute("INSERT INTO cdb_records VALUES (?,?,?,NULL,'fen','puzzle','старе',NULL,'LEGAL_MOVES')",(i,1,i))
            c.execute("INSERT INTO cdb_exercises VALUES (?,?,?,NULL,1)",(i,i,'тактичні комбінації'))
    first = exercise_catalog_query(db,'тактичні комбінації',limit=2,offset=0)
    second = exercise_catalog_query(db,'тактичні комбінації',limit=2,offset=2)
    assert first['total']==3 and [r['id'] for r in first['items']]==[1,2]
    assert second['total']==3 and [r['id'] for r in second['items']]==[3]
    assert exercise_catalog_query(db,'невідома тема')['total']==0
