"""MVP 0.5.3 regression tests. Run on Xubuntu with python-chess."""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path
import pytest
chess = pytest.importorskip('chess')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from exercise053 import authored_moves,migrate_mate_lengths
from stockfish053 import timeline,init_stockfish053,engine_selfplay


def test_attacking_side_moves_white():
    data=authored_moves(chess.STARTING_FEN,['e2e4','e7e5','g1f3'])
    assert (data['attacker_moves'],data['plies'],data['complete']) == (2,3,True)


def test_attacking_side_moves_black():
    b=chess.Board();b.push_uci('e2e4')
    data=authored_moves(b.fen(),['e7e5','g1f3','b8c6'])
    assert data['attacker_moves']==2 and data['plies']==3 and data['complete']


def test_one_ply_source_classified_as_one_author_move():
    st=authored_moves(chess.STARTING_FEN,['e2e4'])
    assert st['attacker_moves']==1


def test_null_move_does_not_become_chess_move():
    st=authored_moves(chess.STARTING_FEN,['e2e4','0000','g1f3'])
    assert not st['complete'] and st['reason']=='null_move' and st['attacker_moves']==1


def test_mate_migration_reclassifies_and_is_idempotent(tmp_path):
    db=tmp_path/'db.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''CREATE TABLE cdb_records(id INTEGER PRIMARY KEY,mainline_json TEXT);
          CREATE TABLE cdb_exercises(id INTEGER PRIMARY KEY,record_id INTEGER,topic TEXT,starting_fen TEXT,mate_in INTEGER);''')
        c.execute('INSERT INTO cdb_records VALUES(1,?)',(json.dumps(['e2e4']),))
        c.execute('INSERT INTO cdb_records VALUES(2,?)',(json.dumps(['e2e4','e7e5','g1f3']),))
        c.execute('INSERT INTO cdb_records VALUES(3,?)',(json.dumps(['e2e4']),))
        for args in [(1,1,'мат',chess.STARTING_FEN,2),(2,2,'мат',chess.STARTING_FEN,1),
                     (3,3,'подвійний удар',chess.STARTING_FEN,None)]:
            c.execute('INSERT INTO cdb_exercises VALUES(?,?,?,?,?)',args)
    preview=migrate_mate_lengths(db,dry_run=True)
    assert preview['changed']==2
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT mate_in FROM cdb_exercises WHERE id=1').fetchone()[0]==2
    actual=migrate_mate_lengths(db)
    assert actual['changed']==2
    assert migrate_mate_lengths(db)['changed']==0
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT mate_in FROM cdb_exercises WHERE id=1').fetchone()[0]==1
        assert c.execute('SELECT mate_in FROM cdb_exercises WHERE id=2').fetchone()[0]==2
        assert c.execute('SELECT mate_in FROM cdb_exercises WHERE id=3').fetchone()[0] is None


def test_timeline_includes_start_and_replayable_each_ply():
    items=timeline(chess.STARTING_FEN,['e2e4','e7e5','g1f3'])
    assert len(items)==4 and [x['ply'] for x in items]==[0,1,2,3]
    assert items[1]['san']=='1.e4'
    assert items[2]['san']=='1...e5'
    assert items[3]['san']=='2.Nf3'
    assert items[0]['fen']==chess.STARTING_FEN


def test_timeline_rejects_illegal_or_null():
    with pytest.raises(ValueError):timeline(chess.STARTING_FEN,['0000'])
    with pytest.raises(ValueError):timeline(chess.STARTING_FEN,['a1a8'])


def test_game_schema_preserves_records_and_is_repeatable(tmp_path):
    db=tmp_path/'db.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY);
         CREATE TABLE cdb_exercises(id INTEGER PRIMARY KEY);
         CREATE TABLE games(id INTEGER PRIMARY KEY,user_id INTEGER,fen TEXT,start_fen TEXT,
           moves TEXT,skill INTEGER,status TEXT,created TEXT);
         INSERT INTO games VALUES(1,1,'start','start','[]',4,'active','today');''')
    init_stockfish053(db);init_stockfish053(db)
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT player_color FROM games WHERE id=1').fetchone()[0]=='white'
        assert c.execute('SELECT COUNT(*) FROM games').fetchone()[0]==1
        assert c.execute("SELECT name FROM sqlite_master WHERE name='stockfish_solutions'").fetchone()


def test_engine_selfplay_limit_validation():
    with pytest.raises(ValueError):engine_selfplay(chess.STARTING_FEN,'/missing/engine',max_plies=81)
    with pytest.raises(ValueError):engine_selfplay(chess.STARTING_FEN,'/missing/engine',think_time=.01)
