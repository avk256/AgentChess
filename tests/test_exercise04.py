"""Regression tests for full exercise catalogue and source-labelled play."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest
pytest.importorskip('chess')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from exercise04 import init_exercises04, available_counts, start_session, make_move, hint


@pytest.fixture
def db(tmp_path):
    p=tmp_path/'test.sqlite3'
    with sqlite3.connect(p) as c:
        c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY);
        CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,mainline_json TEXT,tree_json TEXT);
        CREATE TABLE cdb_exercises(
            id INTEGER PRIMARY KEY,record_id INTEGER,topic TEXT,difficulty INTEGER,
            mate_in INTEGER,starting_fen TEXT,readiness TEXT,answer_uci TEXT,
            validation_method TEXT,review_reason TEXT);
        CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER,record_id INTEGER,
            fen TEXT,topic TEXT,move TEXT,correct INTEGER,created TEXT);
        INSERT INTO users VALUES(1);
        ''')
        starting='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        # An actual non-standard-start position with legal moves: it must stay
        # available as EXPLORE, even though its source provides no move line.
        explore_fen='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'
        c.execute('INSERT INTO cdb_records(id,mainline_json,tree_json) VALUES (?,?,?)',(1,json.dumps(['e2e4']),'{}'))
        c.execute('INSERT INTO cdb_records(id,mainline_json,tree_json) VALUES (?,?,?)',(2,json.dumps([]),'{}'))
        c.execute('INSERT INTO cdb_records(id,mainline_json,tree_json) VALUES (?,?,?)',(3,json.dumps(['e2e4']),'{}'))
        # A book preface mistakenly labelled as an exercise. MVP 0.5.5 filters it out.
        c.execute('INSERT INTO cdb_records(id,mainline_json,tree_json) VALUES (?,?,?)',(4,json.dumps([]),'{}'))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,mate_in,starting_fen,readiness)
                       VALUES (1,1,'мат',2,2,?,'REVIEW_REQUIRED')''',(starting,))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,mate_in,starting_fen,readiness)
                       VALUES (2,2,'базові мати',1,NULL,?,'REVIEW_REQUIRED')''',(explore_fen,))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,mate_in,starting_fen,readiness)
                       VALUES (3,3,'подвійний удар',1,NULL,?,'GUIDED')''',(starting,))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,mate_in,starting_fen,readiness)
                       VALUES (4,4,'базові мати',1,NULL,?,'REVIEW_REQUIRED')''',(starting,))
    init_exercises04(p)
    return p


def test_all_statuses_counted(db):
    # Four catalogue rows, but one standard-start book preface is excluded.
    assert available_counts(db)['total']==3
    assert available_counts(db,'мат',2,2)['total']==1
    assert available_counts(db,'мат',1,2)['total']==0
    assert available_counts(db,'базові мати')['total']==1
    assert available_counts(db,'базові мати')['exploration']==1


def test_unvalidated_mate_two_available_as_source_line(db):
    s=start_session(db,1,'мат',2,2)
    assert s['mode']=='SOURCE_LINE' and s['mate_in']==2
    assert 'answer_uci' not in s and 'mainline' not in s
    wrong=make_move(db,1,s['session_id'],'d2d4')
    assert wrong['correct'] is False and wrong['attempts']==1
    correct=make_move(db,1,s['session_id'],'e2e4')
    assert correct['correct'] is True and correct['finished']


def test_exploration_not_misgraded(db):
    s=start_session(db,1,'базові мати')
    assert s['mode']=='EXPLORE'
    assert s['fen'].split()[1] == 'b'
    a=make_move(db,1,s['session_id'],'e7e5')
    assert a['correct'] is None and a['finished']


def test_hint_does_not_change_chess_position(db):
    s=start_session(db,1,'мат',2,2)
    h=hint(db,1,s['session_id'])
    assert 'e2' in h['hint']
    with sqlite3.connect(db) as c:
        r=c.execute('SELECT current_fen,hint_count FROM exercise_sessions WHERE id=?',(s['session_id'],)).fetchone()
        assert r[0]==s['fen'] and r[1]==1


def test_other_users_cannot_access_session(db):
    s=start_session(db,1,'мат',2,2)
    with pytest.raises(LookupError):make_move(db,2,s['session_id'],'e2e4')
