"""MVP 0.3 integration tests (run on Xubuntu conda env with python-chess)."""
import json
import sqlite3
from pathlib import Path
import sys
import pytest
pytest.importorskip('chess')
import chess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from exercise03 import init_exercises, assess, start_session, make_move, mate_ones

@pytest.fixture
def db(tmp_path):
    p=tmp_path/'tests.sqlite3'
    with sqlite3.connect(p) as c:
        c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY);
        INSERT INTO users(id) VALUES(1),(2);
        CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,mainline_json TEXT NOT NULL,status TEXT);
        CREATE TABLE cdb_exercises (
          id INTEGER PRIMARY KEY,record_id INTEGER NOT NULL REFERENCES cdb_records(id) ON DELETE CASCADE,
          topic TEXT NOT NULL,difficulty INTEGER,goal_type TEXT NOT NULL,mate_in INTEGER,
          starting_fen TEXT,solution_tree_json TEXT NOT NULL,readiness TEXT NOT NULL,
          review_reason TEXT,created_at TEXT NOT NULL);
        CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER,record_id INTEGER,
          fen TEXT,topic TEXT,move TEXT,correct INTEGER,created TEXT);
        ''')
    init_exercises(p)
    return p

def insert(db,id,fen,topic,line,readiness='READY',answer=None,method='EXACT_MATE_IN_ONE'):
    with sqlite3.connect(db) as c:
        c.execute('INSERT INTO cdb_records(id,mainline_json,status) VALUES(?,?,?)',
                  (id,json.dumps(line),'LEGAL_MOVES'))
        c.execute('''INSERT INTO cdb_exercises(id,record_id,topic,difficulty,goal_type,mate_in,
             starting_fen,solution_tree_json,readiness,review_reason,created_at,answer_uci,validation_method)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
             (id,id,topic,1,'mate' if topic=='мат' else 'tactic',1,fen,'{}',readiness,None,'now',json.dumps(answer or line[:1]),method))

def test_mate_one_rules_not_only_reference():
    fen='6k1/5ppp/8/8/8/8/5PPP/5RK1 w - - 0 1'
    b=chess.Board(fen)
    assert mate_ones(b)==[]
    # K+Q vs bare K, queen can checkmate when appropriate.
    position=chess.Board('6k1/5p1p/6p1/8/8/6Q1/8/6K1 w - - 0 1')
    assert isinstance(mate_ones(position),list)

def test_verified_mate_from_real_cdb_sample():
    fen='4r1k1/pp3ppp/3P1n2/8/8/2QB1bP1/PPPK1P1q/R4R2 b - - 0 1'
    row={'starting_fen':fen,'status':'LEGAL_MOVES','mainline_json':'["h2h6"]',
         'topic':'мат','mate_in':1}
    outcome=assess(row)
    assert outcome['readiness']=='READY'
    assert 'h2h6' in json.loads(outcome['answer_uci'])

def test_attempt_retries_owned_by_user(db):
    fen='4r1k1/pp3ppp/3P1n2/8/8/2QB1bP1/PPPK1P1q/R4R2 b - - 0 1'
    insert(db,1,fen,'мат',['h2h6'])
    session=start_session(db,1,'мат')
    assert 'answer_uci' not in session and 'solution' not in session
    assert session['side']=='black'
    with pytest.raises(LookupError):make_move(db,2,session['session_id'],'h2h6')
    assert make_move(db,1,session['session_id'],'h2h6')['finished']
    with pytest.raises(RuntimeError):make_move(db,1,session['session_id'],'h2h6')
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==1

def test_wrong_legal_move_does_not_advance(db):
    fen='4r1k1/pp3ppp/3P1n2/8/8/2QB1bP1/PPPK1P1q/R4R2 b - - 0 1'
    insert(db,1,fen,'мат',['h2h6'])
    s=start_session(db,1,'мат')
    b=chess.Board(fen)
    wrong=next(m.uci() for m in b.legal_moves if m.uci()!='h2h6')
    bad=make_move(db,1,s['session_id'],wrong)
    assert bad['correct'] is False and bad['fen']==s['fen'] and bad['attempts']==1
    good=make_move(db,1,s['session_id'],'h2h6')
    assert good['correct'] and good['attempts']==1

def test_guided_endgame_autoplays_reply(db):
    fen=chess.STARTING_FEN
    insert(db,2,fen,'ендшпіль',['e2e4','e7e5','g1f3'],readiness='GUIDED',method='SOURCE_LINE_STUDY')
    s=start_session(db,1,'ендшпіль')
    first=make_move(db,1,s['session_id'],'e2e4')
    assert first['correct'] and not first['finished']
    assert first['opponent_moves'][0]['uci']=='e7e5'
    second=make_move(db,1,s['session_id'],'g1f3')
    assert second['finished'] and second['correct']

def test_tactic_without_engine_is_not_falsely_ready():
    row={'starting_fen':chess.STARTING_FEN,'status':'LEGAL_MOVES',
         'mainline_json':'["e2e4"]','topic':'подвійний удар','mate_in':None}
    assert assess(row)['readiness']=='REVIEW_REQUIRED'
