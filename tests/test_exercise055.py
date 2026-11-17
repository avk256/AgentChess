"""Regression tests for AgentChess MVP 0.5.5 (SQLite-only, no Stockfish)."""
import json
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from exercise055 import (migrate_endgame_topics,reset_current_exercise,
                         initial_comment,comment_for_line,topic_sources)
from migrate055 import migration_report

START='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
FEN='8/8/8/1kp5/3r4/4K3/8/7R b - - 0 75'


def sample(tmp_path):
    db=tmp_path/'test.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''
          CREATE TABLE cdb_sources(id INTEGER PRIMARY KEY,filename TEXT);
          CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,source_id INTEGER,original_id INTEGER,
              normalized_fen TEXT,mainline_json TEXT,movetext TEXT,tree_json TEXT);
          CREATE TABLE cdb_exercises(id INTEGER PRIMARY KEY,record_id INTEGER,starting_fen TEXT,
              topic TEXT,difficulty INTEGER,mate_in INTEGER);
          CREATE TABLE exercise_sessions(id TEXT PRIMARY KEY,user_id INTEGER,exercise_id INTEGER,
              current_fen TEXT,line_index INTEGER DEFAULT 0,wrong_attempts INTEGER DEFAULT 0,
              finished INTEGER DEFAULT 0,finished_at TEXT,session_type TEXT,hint_count INTEGER DEFAULT 0);
          CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER,record_id INTEGER);
        ''')
        c.executemany('INSERT INTO cdb_sources VALUES (?,?)',[(1,'king_rook_mate.ru.cdb'),(2,'endings_for_beginners.ru.cdb'),(3,'Smyslov_endgame.cdb')])
        c.executemany('INSERT INTO cdb_records VALUES (?,?,?,?,?,?,?)',[
          (1,1,1,FEN,'["d4d8"]','{+Тестова позиція.} Rd8','{"variations":[]}'),
          (2,2,1,FEN,'["d4d8"]','Rd8','{"variations":[]}'),
          (3,3,1,START,'[]','{+ГЛАВА 1. Вступ книги.}','{"variations":[]}'),
        ])
        c.executemany('INSERT INTO cdb_exercises VALUES (?,?,?,?,?,?)',[
          (10,1,FEN,'базові мати',1,None),(11,2,FEN,'ендшпіль',2,None),
        ])
        c.executemany('INSERT INTO exercise_sessions VALUES (?,?,?,?,?,?,?,?,?,?)',[
          ('mine',7,10,'8/8/8/8/8/8/8/8 w - - 0 1',1,2,1,'yesterday','SOURCE_LINE',1),
          ('mine-old',7,10,FEN,0,0,1,'yesterday','SOURCE_LINE',0),
          ('other',8,10,FEN,1,0,1,'yesterday','SOURCE_LINE',0),
          ('other-exercise',7,11,FEN,0,0,1,'yesterday','SOURCE_LINE',0),
        ])
        c.executemany('INSERT INTO attempts VALUES (?,?,?)',[(1,7,1),(2,7,1),(3,8,1),(4,7,2)])
    return db


def test_migration_idempotent_and_preserves_records(tmp_path):
    db=sample(tmp_path)
    assert migrate_endgame_topics(db,dry_run=True)['reclassified']==1
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT topic FROM cdb_exercises WHERE id=10').fetchone()[0]=='базові мати'
    assert migrate_endgame_topics(db)['reclassified']==1
    assert migrate_endgame_topics(db)['reclassified']==0
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT COUNT(*) FROM cdb_records').fetchone()[0]==3
        assert c.execute('SELECT topic FROM cdb_exercises WHERE id=10').fetchone()[0]=='ендшпіль'
        assert c.execute('SELECT COUNT(*) FROM exercise_sessions').fetchone()[0]==4


def test_only_current_user_exercise_is_reset(tmp_path):
    db=sample(tmp_path)
    r=reset_current_exercise(db,7,'mine')
    assert r['fen']==FEN and not r['finished']
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM exercise_sessions WHERE user_id=7 AND exercise_id=10").fetchone()[0]==1
        assert c.execute("SELECT finished,line_index,wrong_attempts FROM exercise_sessions WHERE id='mine'").fetchone()==(0,0,0)
        assert c.execute("SELECT COUNT(*) FROM exercise_sessions WHERE user_id=8").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM exercise_sessions WHERE id='other-exercise'").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM attempts WHERE user_id=7 AND record_id=1").fetchone()[0]==0
        assert c.execute("SELECT COUNT(*) FROM attempts WHERE user_id=8").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM attempts WHERE user_id=7 AND record_id=2").fetchone()[0]==1
    with pytest.raises(LookupError):reset_current_exercise(db,8,'mine')


def test_book_preface_not_counted_as_task(tmp_path):
    db=sample(tmp_path)
    t=topic_sources(db)
    assert t['total']==2
    assert sum(x['count'] for x in t['topics'] if x['topic']=='ендшпіль')==1
    assert 'Вступ книги' in initial_comment('{+Вступ книги.}')


def test_author_comments_follow_line():
    tree={'variations':[{'uci':'a2a4','comment':'Перший план','children':[
       {'uci':'a7a5','comment':'Альтернатива чорних','children':[]}]}]}
    t=json.dumps(tree)
    assert comment_for_line('{+Позиція стратегічна} 1.a4 a5',t,'["a2a4","a7a5"]',0)=='Позиція стратегічна'
    assert comment_for_line('',t,'["a2a4","a7a5"]',1)=='Перший план'
    assert comment_for_line('',t,'["a2a4","a7a5"]',2)=='Альтернатива чорних'


def test_migration_report_keeps_raw_data(tmp_path):
    db=sample(tmp_path)
    r=migration_report(db,dry_run=True)
    assert r['dry_run'] is True and r['integrity_check']=='ok'
    assert r['source_records']==3 and r['exercises']==2
    assert r['hidden_standard_start_book_text']==1


def test_catalog_filter_uses_exercise_topic(tmp_path):
    from catalog import init_catalog, connect, catalog_query
    db=tmp_path/'catalog.sqlite3'
    init_catalog(db)
    with connect(db) as c:
        c.execute("INSERT INTO cdb_sources(id,filename,level,sha256,origin_path,metadata_json,imported_at) VALUES(1,'School2.ru.cdb','середній','abc','School2.ru.cdb','{}','today')")
        c.execute("""INSERT INTO cdb_records(
           id,source_id,original_id,origin_index,raw_json,record_type,topic,status,
           normalized_fen,mainline_json,errors_json,difficulty)
           VALUES(1,1,1,1,'{}','puzzle','тактика','LEGAL_MOVES',?,'["d4d8"]','[]',2)""",(FEN,))
        c.execute("""INSERT INTO cdb_exercises(
           id,record_id,topic,difficulty,goal_type,starting_fen,
           solution_tree_json,readiness,created_at)
           VALUES(1,1,'тактичні комбінації',2,'source_line',?,'{}','GUIDED','today')""",(FEN,))
    assert catalog_query(db,topic='тактичні комбінації')['total']==1
    assert catalog_query(db,topic='тактика')['total']==0
