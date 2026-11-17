"""Regression tests for session-bound source viewer and progress reset.
Run with python -m pytest tests/ -v in Conda agentchess.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
chess = pytest.importorskip('chess')
from exercise042 import build_solution_steps, session_solution, reset_user_progress


def test_three_ply_source_solution():
    # discovered.ru.cdb, record 22, documented from actual CDB.
    fen='3r2k1/pp2qp1p/2p3p1/4b3/P3Q3/4P2P/5PP1/BR4K1 b - - 0 1'
    seq=['e5h2','g1h2','e7e4']
    r=build_solution_steps(fen,json.dumps(seq))
    assert r['complete']
    assert len(r['steps'])==4
    assert [s['san'] for s in r['steps'][1:]]==['Bh2+','Kxh2','Qxe4']
    assert r['steps'][0]['fen'].split(' ')[0]==fen.split(' ')[0]
    assert r['steps'][-1]['fen'] != fen


def test_null_marker_stops_instead_of_fake_move():
    fen='8/8/5k2/8/p7/8/1PK5/8 w - - 0 1'
    r=build_solution_steps(fen,json.dumps(['0000','c2c3']))
    assert not r['complete']
    assert r['total_source_plies']==2
    assert len(r['steps'])==1
    assert '0000' in r['note']


def test_empty_solution_is_visible_as_position_only():
    fen=chess.STARTING_FEN
    r=build_solution_steps(fen,'[]')
    assert r['steps'] and len(r['steps'])==1
    assert not r['complete']


def test_reset_scoped_to_authenticated_user(tmp_path):
    db=tmp_path/'test.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER);
        CREATE TABLE exercise_sessions(id TEXT PRIMARY KEY,user_id INTEGER);
        CREATE TABLE games(id INTEGER PRIMARY KEY,user_id INTEGER);
        CREATE TABLE cdb_records(id INTEGER PRIMARY KEY);
        INSERT INTO attempts(user_id) VALUES(1),(2);
        INSERT INTO exercise_sessions(id,user_id) VALUES('a',1),('b',2);
        INSERT INTO games(user_id) VALUES(1),(2);
        INSERT INTO cdb_records(id) VALUES(99);''')
    result=reset_user_progress(db,1)
    assert result['deleted']=={'attempts':1,'exercise_sessions':1,'games':1}
    with sqlite3.connect(db) as c:
        for table in ('attempts','exercise_sessions','games'):
            assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==1
            assert c.execute(f'SELECT user_id FROM {table}').fetchone()[0]==2
        assert c.execute('SELECT COUNT(*) FROM cdb_records').fetchone()[0]==1
