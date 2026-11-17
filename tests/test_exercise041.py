"""Regression tests for source continuation, origin and SF handoff."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest
chess = pytest.importorskip('chess')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from exercise041 import init_exercises041, start_session, make_move, catalog_solution, source_line_summary


@pytest.fixture
def db(tmp_path):
    p=tmp_path/'test.sqlite3'
    with sqlite3.connect(p) as c:
        c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY);
        CREATE TABLE cdb_sources(id INTEGER PRIMARY KEY,filename TEXT);
        CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,source_id INTEGER,original_id INTEGER,
            normalized_fen TEXT,mainline_json TEXT,tree_json TEXT,movetext TEXT);
        CREATE TABLE cdb_exercises(
            id INTEGER PRIMARY KEY,record_id INTEGER,topic TEXT,difficulty INTEGER,
            mate_in INTEGER,starting_fen TEXT,readiness TEXT,answer_uci TEXT,
            validation_method TEXT,review_reason TEXT);
        CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER,record_id INTEGER,
            fen TEXT,topic TEXT,move TEXT,correct INTEGER,created TEXT);
        INSERT INTO users VALUES(1);
        INSERT INTO cdb_sources VALUES(1,'discovered.ru.cdb');
        ''')
        fen=chess.STARTING_FEN
        # two player moves with a recorded opponent reply, valid and replayable
        line=json.dumps(['e2e4','e7e5','g1f3'])
        c.execute('INSERT INTO cdb_records VALUES(?,?,?,?,?,?,?)',
                  (1,1,16,fen,line,'{"variations":[]}', '1.e4 e5 2.Nf3'))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,mate_in,starting_fen,
                      readiness,answer_uci,validation_method)
                      VALUES(1,1,'відкритий напад',1,NULL,?,'READY',?,
                      'STOCKFISH_TOP1_GAP')''',(fen,json.dumps(['e2e4'])))
    init_exercises041(p)
    return p


def test_line_is_full_and_has_san():
    text=source_line_summary(chess.STARTING_FEN,json.dumps(['e2e4','e7e5','g1f3']))
    assert text['plies']==3 and text['complete']
    assert 'e4' in text['san'] and 'Nf3' in text['san']


def test_verified_first_move_does_not_end_source_combination(db):
    session=start_session(db,1,'відкритий напад')
    assert session['source_file']=='discovered.ru.cdb'
    assert session['source_record_id']==16
    assert session['source_plies']==3
    assert session['mode']=='SOURCE_LINE'
    first=make_move(db,1,session['session_id'],'e2e4')
    assert first['correct'] and not first['finished']
    assert first['opponent_moves'][0]['uci']=='e7e5'
    final=make_move(db,1,session['session_id'],'g1f3')
    assert final['finished'] and 'Nf3' in final['source_solution_san']


def test_catalog_shows_original_solution(db):
    data=catalog_solution(db,1)
    assert data['source']=='discovered.ru.cdb'
    assert data['source_record_id']==16
    assert data['plies']==3 and 'e5' in data['line_san']
    assert '1.e4' in data['original_movetext']
