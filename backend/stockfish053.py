"""Engine-vs-engine demonstration and reproducible, server-authoritative timelines.

Important: a capped self-play line is an engine DEMONSTRATION, not a proof of
forced mate or perfect play. User and analysis timelines are never conflated.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import chess
import chess.engine
from exercise03 import connect


def timeline(start_fen, uci_moves):
    b=chess.Board(start_fen)
    result=[{'ply':0,'fen':b.fen(),'uci':None,'san':'Початкова позиція','turn':'white' if b.turn else 'black'}]
    for idx,code in enumerate(uci_moves or [],1):
        move=chess.Move.from_uci(code)
        if move not in b.legal_moves: raise ValueError(f'Помилковий хід в історії, півхід {idx}: {code}')
        text=f'{b.fullmove_number}{"." if b.turn else "..."}{b.san(move)}'
        b.push(move)
        result.append({'ply':idx,'fen':b.fen(),'uci':code,'san':text,'turn':'white' if b.turn else 'black'})
    return result


def init_stockfish053(db):
    with connect(db) as c:
        cols={r['name'] for r in c.execute('PRAGMA table_info(games)')}
        if 'player_color' not in cols:
            c.execute("ALTER TABLE games ADD COLUMN player_color TEXT DEFAULT 'white'")
        c.execute('''CREATE TABLE IF NOT EXISTS stockfish_solutions (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          exercise_id INTEGER NOT NULL REFERENCES cdb_exercises(id) ON DELETE CASCADE,
          start_fen TEXT NOT NULL, moves TEXT NOT NULL,
          status TEXT NOT NULL, max_plies INTEGER NOT NULL,
          think_time REAL NOT NULL, created TEXT NOT NULL
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS sf_solution_user ON stockfish_solutions(user_id,id)')


def engine_selfplay(start_fen,engine_path,max_plies=24,think_time=.12):
    if not 2<=max_plies<=80:raise ValueError('Дозволено 2–80 півходів')
    if not .05<=think_time<=.4:raise ValueError('Час аналізу на хід: 0.05–0.4 с')
    if not Path(engine_path).is_file():raise FileNotFoundError('Stockfish не знайдено')
    b=chess.Board(start_fen)
    if not b.is_valid():raise ValueError('Некоректна початкова позиція')
    moves=[]
    with chess.engine.SimpleEngine.popen_uci(engine_path,timeout=30) as engine:
        # No reduced Skill Level: engine finds its own continuation for both sides.
        if 'Skill Level' in engine.options:
            engine.configure({'Skill Level':20})
        while len(moves)<max_plies and not b.is_game_over(claim_draw=True):
            best=engine.play(b,chess.engine.Limit(time=think_time)).move
            if best not in b.legal_moves: raise RuntimeError('Stockfish повернув нелегальний хід')
            b.push(best);moves.append(best.uci())
    return {'moves':moves,
            'status':b.result(claim_draw=True) if b.is_game_over(claim_draw=True) else 'max_plies_reached',
            'timeline':timeline(start_fen,moves),
            'warning':('Досягнуто обмеження довжини; це демонстрація, а не доказ мату.'
                       if not b.is_game_over(claim_draw=True) else 'Партія завершилася за шаховими правилами.')}


def save_solution(db,user_id,exercise_id,start_fen,result,max_plies,think_time):
    with connect(db) as c:
        cur=c.execute('''INSERT INTO stockfish_solutions
          (user_id,exercise_id,start_fen,moves,status,max_plies,think_time,created)
          VALUES(?,?,?,?,?,?,?,?)''',
          (user_id,exercise_id,start_fen,json.dumps(result['moves']),result['status'],max_plies,
           think_time,dt.datetime.now(dt.timezone.utc).isoformat()))
        return cur.lastrowid
