"""AgentChess 0.4.1: complete source continuations and exercise provenance.

Mainline is a source-authored illustrative variation, NOT a proof of unique
solution. Verified first moves may still be followed by source continuations.
"""
from __future__ import annotations
import json
import chess
from exercise053 import authored_moves, move_word
from exercise04 import (init_exercises04, available_counts, hint,
                        start_session as _start04, make_move as _move04, connect, _line)


def source_line_summary(fen, mainline_json):
    """Produce human-readable SAN line from CDB UCI mainline, no guessing."""
    try:
        board = chess.Board(fen)
        raw = json.loads(mainline_json or '[]')
        san = []
        for code in raw:
            move = chess.Move.from_uci(code)
            if move not in board.legal_moves:
                return {'plies': len(san), 'san': ' '.join(san), 'complete': False}
            prefix = f'{board.fullmove_number}.' if board.turn else f'{board.fullmove_number}...'
            san.append(prefix + board.san(move))
            board.push(move)
        return {'plies': len(raw), 'san': ' '.join(san), 'complete': True}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {'plies': 0, 'san': '', 'complete': False}


def init_exercises041(db):
    init_exercises04(db)
    # Migration adds no foreign keys or destructive operations.


def _metadata(c, sid, uid):
    row = c.execute('''SELECT s.id, e.id AS exercise_id, e.topic, e.readiness,
           e.validation_method, e.starting_fen, e.record_id, r.source_id,
           r.original_id, r.mainline_json, r.tree_json, src.filename
           FROM exercise_sessions s
           JOIN cdb_exercises e ON e.id=s.exercise_id
           JOIN cdb_records r ON r.id=e.record_id
           JOIN cdb_sources src ON src.id=r.source_id
           WHERE s.id=? AND s.user_id=?''', (sid, uid)).fetchone()
    if not row: raise LookupError('Сесію не знайдено')
    canonical = _line(row)
    line = source_line_summary(row['starting_fen'], json.dumps(canonical))
    count = authored_moves(row['starting_fen'], canonical)
    line['attacker_moves'] = count['attacker_moves'] if count['complete'] else None
    line['replay_complete'] = count['complete']
    tree_count = 0
    try:
        tree = json.loads(row['tree_json'] or '{}')
        tree_count = len(tree.get('variations') or [])
    except (ValueError, TypeError): pass
    return row, line, tree_count


def start_session(db, user_id, topic, difficulty=None, mate_in=None):
    result = _start04(db, user_id, topic, difficulty, mate_in)
    if result is None: return None
    with connect(db) as c:
        row, line, branches = _metadata(c, result['session_id'], user_id)
        verified_first = (row['readiness'] == 'READY' and
                          row['validation_method'] == 'STOCKFISH_TOP1_GAP')
        # Critical fix: a strong *first* move is not the complete combination.
        # Mate-in-one exact verification remains a single-move exercise.
        if verified_first and line['plies'] > 1:
            c.execute("UPDATE exercise_sessions SET session_type='SOURCE_LINE' WHERE id=?",
                      (result['session_id'],))
            result['mode'] = 'SOURCE_LINE'
        count=line['attacker_moves']
        if count is None:
            result['goal'] += ' Кількість ходів атакуючої сторони у джерелі не визначена (неповна головна лінія).'
        elif topic == 'мат':
            # The mate filter is derived from the SAME author-side count.
            pass
        else:
            result['goal'] += f' В авторському рішенні сторона, яка починає, робить {count} {move_word(count)}.'
        result.update({
            'source_file':row['filename'], 'source_record_id':row['original_id'],
            'record_id':row['record_id'], 'source_id':row['source_id'],
            'source_plies':line['plies'], 'source_full_line':line['complete'],
            'source_attacker_moves':line['attacker_moves'],
            'source_variations':branches,
            'verified_first_move':bool(verified_first),
            'source_note':('У CDB записаний лише перший хід; продовження можна дослідити зі Stockfish.'
                           if line['plies'] == 1 else
                           f'Авторська головна лінія: {line["plies"]} півходів. '
                           'Перший хід може бути перевірений Stockfish, але інші захисти не доведені.'),
        })
    return result


def make_move(db, user_id, session_id, move_text):
    outcome = _move04(db, user_id, session_id, move_text)
    with connect(db) as c:
        row, line, _ = _metadata(c, session_id, user_id)
        session = c.execute('SELECT line_index,finished FROM exercise_sessions WHERE id=?',
                            (session_id,)).fetchone()
    outcome['source_total_plies'] = line['plies']
    outcome['source_played_plies'] = session['line_index']
    if outcome['finished']:
        # Reveal only after completion. This is the historical line, not a proof.
        outcome['source_solution_san'] = line['san']
    return outcome


def catalog_solution(db, record_id):
    with connect(db) as c:
        row = c.execute('''SELECT r.id,r.original_id,r.source_id,r.normalized_fen,
                              r.mainline_json,r.movetext,r.tree_json,s.filename
                           FROM cdb_records r JOIN cdb_sources s ON s.id=r.source_id
                           WHERE r.id=?''',(record_id,)).fetchone()
    if row is None: raise LookupError('Запис не знайдено')
    # From source position. Original text is intentionally shown only in explicit
    # catalogue view, not in exercise-start responses.
    line = source_line_summary(row['normalized_fen'], row['mainline_json'])
    try: tree = json.loads(row['tree_json'] or '{}')
    except (TypeError, ValueError): tree = {}
    return {'record_id':row['id'],'source':row['filename'],
            'source_record_id':row['original_id'],
            'source_id':row['source_id'],'fen':row['normalized_fen'],
            'line_san':line['san'],'plies':line['plies'],
            'line_valid':line['complete'],
            'branches_from_start':len(tree.get('variations') or []),
            'original_movetext':row['movetext'] or '',
            'note':'Авторський запис. Не доводить єдиність або оптимальність усіх ходів.'}
