"""Catalog 0.5.9: topic -> CDB -> original source task number."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from catalog import exercise_catalog_query, exercise_catalog_sources, exercise_catalog_numbers


def make_db(tmp_path):
    db = tmp_path / 'catalog.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''
          CREATE TABLE cdb_sources(id INTEGER PRIMARY KEY, filename TEXT);
          CREATE TABLE cdb_records(id INTEGER PRIMARY KEY, source_id INTEGER, original_id INTEGER,
              event TEXT, normalized_fen TEXT, record_type TEXT, elo INTEGER, status TEXT);
          CREATE TABLE cdb_exercises(id INTEGER PRIMARY KEY, record_id INTEGER, topic TEXT,
              mate_in INTEGER, difficulty INTEGER);
        ''')
        c.executemany('INSERT INTO cdb_sources VALUES (?,?)',
                      [(1,'double_attack.ru.cdb'),(2,'other.ru.cdb'),(3,'polgar.ru.cdb')])
        c.executemany('INSERT INTO cdb_records VALUES (?,?,?,?,?,?,?,?)', [
            (10,1,21,None,'fen','puzzle',1000,'LEGAL_MOVES'),
            (11,1,22,None,'fen','puzzle',1100,'LEGAL_MOVES'),
            (12,2,21,None,'fen','puzzle',1200,'LEGAL_MOVES'),
            (13,3,3041,'Мат в 2 хода','fen','puzzle',None,'LEGAL_MOVES')])
        c.executemany('INSERT INTO cdb_exercises VALUES (?,?,?,?,?)', [
            (100,10,'подвійний удар',None,1),
            (101,11,'подвійний удар',None,2),
            (102,12,'подвійний удар',None,1),
            (103,13,'мат',1,1)])
    return db


def test_sources_are_filtered_by_topic(tmp_path):
    db=make_db(tmp_path)
    got=exercise_catalog_sources(db,'подвійний удар')['sources']
    assert [(s['filename'],s['exercises']) for s in got] == [
        ('double_attack.ru.cdb',2),('other.ru.cdb',1)]
    assert exercise_catalog_sources(db,'мат')['sources'][0]['filename']=='polgar.ru.cdb'


def test_original_numbers_not_global_ids(tmp_path):
    db=make_db(tmp_path)
    nums=exercise_catalog_numbers(db,'подвійний удар',1)['numbers']
    assert nums==[21,22]
    assert 100 not in nums and 10 not in nums
    r=exercise_catalog_query(db,'подвійний удар',source_id=1,original_id=21)
    assert r['total']==1 and r['items'][0]['id']==10
    assert r['items'][0]['exercise_id']==100


def test_page_and_count_use_same_filters(tmp_path):
    db=make_db(tmp_path)
    assert exercise_catalog_query(db,'подвійний удар')['total']==3
    r=exercise_catalog_query(db,'подвійний удар',limit=1,offset=1,source_id=1)
    assert r['total']==2 and len(r['items'])==1
    assert r['items'][0]['original_id']==22
    assert exercise_catalog_query(db,'подвійний удар',source_id=1,original_id=999)['total']==0
    assert exercise_catalog_query(db,'мат',source_id=3,original_id=3041)['total']==1


def test_frontend_filters_are_canonical_and_not_the_label():
    page=(Path(__file__).resolve().parents[1] / 'frontend' / 'index.html').read_text()
    for target in ('catTopic','catSource','catNumber','catNumberInput'):
        assert f'id="{target}"' in page
    assert "q.set('source_id',$('catSource').value)" in page
    assert "q.set('original_id',num)" in page
    assert "'/exercises/catalog/sources?'" in page
    assert "'/exercises/catalog/numbers?'" in page


def test_real_database_if_available():
    db=Path(__file__).resolve().parents[1] / 'data' / 'agentchess.sqlite3'
    if not db.exists():
        pytest.skip('Full CDB database remains on the user Xubuntu machine')
    with sqlite3.connect(db) as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'cdb_exercises','cdb_sources','cdb_records'} <= tables:
        pytest.skip('Full CDB schema not present in local test DB')
    assert exercise_catalog_query(db,'подвійний удар')['total'] > 0
    sources=exercise_catalog_sources(db,'подвійний удар')['sources']
    assert sources
    source_id=sources[0]['source_id']
    nums=exercise_catalog_numbers(db,'подвійний удар',source_id)['numbers']
    assert nums
    assert exercise_catalog_query(db,'подвійний удар',source_id=source_id,original_id=nums[0])['total'] >= 1
