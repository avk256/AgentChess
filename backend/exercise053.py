"""AgentChess 0.5.3: derive author-side move count from CDB mainlines.

The count is the number of *playable* moves made by the side to move in
starting_fen. It is NOT a proof of forced mate or a Stockfish estimate.
"""
from __future__ import annotations
import argparse
import json
import chess
from exercise03 import connect
from exercise04 import _line


def move_word(n):
    return ('хід' if n % 10 == 1 and n % 100 != 11 else
            'ходи' if n % 10 in (2,3,4) and n % 100 not in (12,13,14) else 'ходів')


def authored_moves(starting_fen, codes):
    """Return author attacker moves, valid plies and whether replay is complete.

    A PGN null-move 0000 and an illegal move terminate playback; never credit
    invented or invalid moves toward the source's exercise length.
    """
    try:
        board = chess.Board(starting_fen)
        if not board.is_valid():
            return {'attacker_moves':0,'plies':0,'complete':False,'reason':'invalid_fen'}
    except (TypeError, ValueError):
        return {'attacker_moves':0,'plies':0,'complete':False,'reason':'invalid_fen'}
    attacker = board.turn
    count = plies = 0
    for code in codes or []:
        if code == '0000':
            return {'attacker_moves':count,'plies':plies,'complete':False,'reason':'null_move'}
        try:
            move = chess.Move.from_uci(code)
            if move not in board.legal_moves:
                return {'attacker_moves':count,'plies':plies,'complete':False,'reason':'illegal_move'}
        except (TypeError, ValueError):
            return {'attacker_moves':count,'plies':plies,'complete':False,'reason':'invalid_uci'}
        if board.turn == attacker:
            count += 1
        board.push(move)
        plies += 1
    return {'attacker_moves':count,'plies':plies,'complete':True,'reason':None}


def migrate_mate_lengths(db, *, dry_run=False):
    """Reclassify ONLY mate exercises using playable CDB author mainline.

    Safe on databases with earlier source IDs, exercise sessions and progress.
    It never alters the source records; a rerun is idempotent.
    """
    changes=[]; invalid=[]; distribution={}
    with connect(db) as conn:
        rows=conn.execute('''SELECT e.id,e.mate_in,e.starting_fen,r.mainline_json
          FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
          WHERE e.topic='мат' ORDER BY e.id''').fetchall()
        for row in rows:
            try: raw=json.loads(row['mainline_json'] or '[]')
            except (TypeError,ValueError): raw=[]
            st=authored_moves(row['starting_fen'],raw)
            # A null or partial line is not an authoritative count of solution length.
            count=st['attacker_moves'] if st['complete'] and st['attacker_moves'] else None
            key=str(count) if count is not None else 'unknown'
            distribution[key]=distribution.get(key,0)+1
            if not st['complete']:
                invalid.append({'exercise_id':row['id'],'reason':st['reason']})
            if row['mate_in']!=count:
                changes.append((count,row['id']))
        if not dry_run:
            conn.executemany('UPDATE cdb_exercises SET mate_in=? WHERE id=?',changes)
    return {'dry_run':dry_run,'total_mate_exercises':len(rows),
            'changed':len(changes),'distribution':distribution,
            'incomplete_lines':len(invalid),'incomplete_samples':invalid[:20],
            'rule':'mate_in = number of attacker moves in complete CDB mainline, not a proof of mate'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--db',required=True)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--out')
    a=p.parse_args()
    report=migrate_mate_lengths(a.db,dry_run=a.dry_run)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if a.out:
        from pathlib import Path
        out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
