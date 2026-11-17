"""MVP 0.4.2: read-only step-by-step study of the *source* mainline.

A PGN '--' is represented as UCI 0000 by python-chess. It is a source
placeholder, NOT an actual move, so do not fabricate a new position after it.
The viewer stops and points to the original CDB/variations for further study.
"""
from __future__ import annotations
import json
import sqlite3
import chess
from exercise04 import connect


def build_solution_steps(initial_fen: str, mainline_json: str | None):
    try:
        codes=json.loads(mainline_json or '[]')
        if not isinstance(codes,list):
            raise ValueError('mainline_json must be an array')
        board=chess.Board(initial_fen)
        if not board.is_valid():
            raise ValueError('Некоректний початковий FEN')
    except (ValueError,TypeError,json.JSONDecodeError) as exc:
        return {'steps':[], 'complete':False, 'note':str(exc), 'total_source_plies':0}
    steps=[{'index':0,'fen':board.fen(),'san':'','uci':'','label':'Початкова позиція'}]
    note='Головна авторська лінія CDB. Інші варіанти можуть існувати.'
    complete=True
    for i,code in enumerate(codes,1):
        if code=='0000':
            complete=False
            note=(f'На півході {i} джерело містить позначку «--» (0000) — '
                  'умовний/пропущений хід. Перегляд головної лінії зупинено; '
                  'можливі продовження збережені у варіантах CDB.')
            break
        try:
            move=chess.Move.from_uci(code)
            if move not in board.legal_moves:
                raise ValueError('нелегальний хід')
            san=board.san(move)
            label=(f'{board.fullmove_number}.' if board.turn else f'{board.fullmove_number}...')+san
            board.push(move)
            steps.append({'index':i,'fen':board.fen(),'san':san,'uci':code,'label':label})
        except (ValueError,TypeError):
            complete=False
            note=f'На півході {i} неможливо легально виконати {code!r}; решту лінії не відтворено.'
            break
    if not codes:
        complete=False
        note='У цьому записі немає головної послідовності ходів. Перегляньте позицію і джерело.'
    return {'steps':steps,'complete':complete,'note':note,'total_source_plies':len(codes)}


def session_solution(db, user_id:int, session_id:str):
    with connect(db) as c:
        row=c.execute('''SELECT s.exercise_id, e.starting_fen, e.topic,
                    r.mainline_json,r.original_id,r.tree_json,src.filename
                    FROM exercise_sessions s
                    JOIN cdb_exercises e ON e.id=s.exercise_id
                    JOIN cdb_records r ON r.id=e.record_id
                    JOIN cdb_sources src ON src.id=r.source_id
                    WHERE s.id=? AND s.user_id=?''',(session_id,user_id)).fetchone()
        if not row: raise LookupError('Сесію вправи не знайдено')
        result=build_solution_steps(row['starting_fen'],row['mainline_json'])
        result.update({'exercise_id':row['exercise_id'],'topic':row['topic'],
                       'source':row['filename'],'source_record_id':row['original_id']})
        try:
            tree=json.loads(row['tree_json'] or '{}')
            result['root_variations']=len(tree.get('variations') or [])
        except (ValueError,TypeError,AttributeError):
            result['root_variations']=0
        return result


def reset_user_progress(db, user_id:int, include_games:bool=True):
    """Only the authenticated user's history is deleted. Never touch CDB tables."""
    with connect(db) as c:
        deleted={}
        for table in ('attempts','exercise_sessions') + (('games',) if include_games else ()):
            deleted[table]=c.execute(f'SELECT COUNT(*) FROM {table} WHERE user_id=?',(user_id,)).fetchone()[0]
            c.execute(f'DELETE FROM {table} WHERE user_id=?',(user_id,))
        return {'deleted':deleted, 'scope':'current_user', 'catalog_untouched':True}
