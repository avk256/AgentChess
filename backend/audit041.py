"""Read-only 0.4.1 CDB audit: source-line completeness and legal continuations.

Run: python backend/audit041.py --db data/agentchess.sqlite3 --out data/audit_041.json
Requires python-chess in the project's conda environment. Does NOT mutate SQLite.
"""
import argparse
import collections
import json
import sqlite3
from pathlib import Path

import chess


def audit(db):
    con = sqlite3.connect(f'file:{Path(db).resolve()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    topics = collections.defaultdict(lambda: collections.Counter())
    examples = collections.defaultdict(list)
    errors = []
    sql = '''SELECT e.id, e.topic, e.starting_fen, e.readiness,
                    r.mainline_json, r.tree_json, r.original_id, s.filename
             FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
             JOIN cdb_sources s ON s.id=r.source_id ORDER BY e.id'''
    for row in con.execute(sql):
        topic = row['topic']
        counter = topics[topic]
        counter['total'] += 1
        try: line = json.loads(row['mainline_json'] or '[]')
        except (TypeError, ValueError): line = []
        n = len(line)
        counter['zero_ply' if n == 0 else 'one_ply' if n == 1 else 'multi_ply'] += 1
        counter['source_plies'] += n
        try:
            tree = json.loads(row['tree_json'] or '{}')
            if len(tree.get('variations') or []) > 1: counter['multiple_root_variations'] += 1
        except (TypeError, ValueError): counter['invalid_tree_json'] += 1
        if n == 1 and len(examples[topic]) < 6:
            examples[topic].append({'exercise_id':row['id'], 'source':row['filename'],
                                    'source_record_id':row['original_id'],
                                    'single_move_uci':line[0]})
        try:
            board = chess.Board(row['starting_fen'])
            if not board.is_valid(): raise ValueError('invalid starting FEN')
            for ply, uci in enumerate(line, start=1):
                move = chess.Move.from_uci(uci)
                if move not in board.legal_moves:
                    raise ValueError(f'illegal source ply {ply}: {uci}')
                board.push(move)
            counter['legally_replayable'] += 1
        except Exception as ex:
            counter['not_replayable'] += 1
            if len(errors) < 100:
                errors.append({'exercise_id':row['id'],'source':row['filename'],
                               'source_record_id':row['original_id'],'error':str(ex)})
    con.close()
    return {'total':sum(t['total'] for t in topics.values()),
            'topics':{k:dict(v) for k,v in sorted(topics.items())},
            'one_ply_samples':dict(examples),
            'replay_errors_first_100':errors,
            'notes':['one_ply refers to the AUTHOR mainline, not the absence of alternatives',
                     'legally_replayable is not a proof of tactical motif or optimal play',
                     'mainline only; variations are retained in tree_json, not checked here']}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--db',default='data/agentchess.sqlite3')
    p.add_argument('--out',default='data/audit_041.json')
    a=p.parse_args()
    result=audit(a.db)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'total':result['total'],'topics':result['topics'],
                      'errors':len(result['replay_errors_first_100'])},ensure_ascii=False,indent=2))
