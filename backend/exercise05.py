"""AgentChess MVP 0.5: complete CDB variation browsing and new source-based exercises.

Never interpret a null PGN move (0000, --) as a legal chess move.
Only LEGAL_MOVES positions with non-null playable author variations become new exercises.
New lessons represent SOURCE_LINE study, not objective verification by engine.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import chess

from exercise04 import connect, init_exercises04

# Curatorial classification, confirmed against the original CDB records and chapters.
from exercise05_topics import SOURCE_TOPICS, NEW_TOPICS


def legal_first_variation(fen: str, tree_json: str | None) -> list[str]:
    """Find a single legal root-to-leaf line; never cross a null move.

    This is used for newly added source-study exercises, not for proving solutions.
    """
    try:
        board = chess.Board(fen)
        if not board.is_valid():
            return []
        roots = json.loads(tree_json or '{}').get('variations', [])
    except (ValueError, TypeError, AttributeError):
        return []
    def visit(choices, b, depth=0):
        if depth >= 150:
            return []
        for node in choices or []:
            u = node.get('uci') if isinstance(node, dict) else None
            if not u or u == '0000':
                continue
            try:
                mv = chess.Move.from_uci(u)
                if mv not in b.legal_moves:
                    continue
            except (ValueError, TypeError):
                continue
            nxt=b.copy(stack=False)
            nxt.push(mv)
            return [u] + visit(node.get('children',[]), nxt, depth + 1)
        return []
    return visit(roots, board)


def expand_sources(db, *, dry_run=False):
    """Idempotent, non-destructive insertion of new exercises for 15 source CDBs.

    Does not rewrite source records, sessions or existing exercises.
    """
    init_exercises04(db)
    counts = {}
    added = 0
    reason_counts = {'already_exists': 0, 'not_legal': 0, 'no_usable_line': 0}
    with connect(db) as c:
        sources = list(c.execute('SELECT id,filename FROM cdb_sources ORDER BY filename'))
        for source in sources:
            topic = SOURCE_TOPICS.get(source['filename'])
            if not topic:
                continue
            counts[ source['filename'] ]={'topic':topic,'total_records':0,'added':0,'skipped':0}
            records = c.execute('''SELECT r.id,r.normalized_fen,r.status,r.mainline_json,r.tree_json,
                                r.difficulty,r.original_id,e.id existing_id
                                FROM cdb_records r LEFT JOIN cdb_exercises e ON e.record_id=r.id
                                WHERE r.source_id=? ORDER BY r.id''', (source['id'],))
            for row in records:
                d=counts[source['filename']];d['total_records']+=1
                if row['existing_id'] is not None:
                    reason_counts['already_exists'] += 1;d['skipped']+=1;continue
                if row['status'] != 'LEGAL_MOVES' or not row['normalized_fen']:
                    reason_counts['not_legal']+=1;d['skipped']+=1;continue
                line=legal_first_variation(row['normalized_fen'], row['tree_json'])
                if not line:
                    reason_counts['no_usable_line']+=1;d['skipped']+=1;continue
                if not dry_run:
                    c.execute('''INSERT OR IGNORE INTO cdb_exercises
                        (record_id,topic,difficulty,goal_type,mate_in,starting_fen,solution_tree_json,
                         readiness,review_reason,created_at,validation_method,answer_uci)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (row['id'],topic,row['difficulty'] or 2,'SOURCE_LINE_STUDY',None,
                          row['normalized_fen'],row['tree_json'] or '{}','GUIDED',
                          'Матеріал з CDB: авторський варіант; оптимальність не доведена',
                          dt.datetime.now(dt.timezone.utc).isoformat(), 'SOURCE_LINE_STUDY', json.dumps([line[0]])))
                added+=1;d['added']+=1
    return {'dry_run':dry_run, 'new_exercises':added,'sources':counts,'skipped_reasons':reason_counts,
            'explanation':'Оригінальні записи та наявні вправи залишаються без змін. Нові вправи — проходження авторського варіанта.'}


def source_study_line(db, record_id):
    """Dynamic canonical line for new CDB study topics; prefer the stored mainline when legal."""
    with connect(db) as c:
        r=c.execute('SELECT normalized_fen,mainline_json,tree_json FROM cdb_records WHERE id=?',(record_id,)).fetchone()
        if r is None:
            return []
        try:
            main=json.loads(r['mainline_json'] or '[]')
            board=chess.Board(r['normalized_fen'])
            if main and all(isinstance(x,str) and x!='0000' for x in main):
                for u in main:
                    m=chess.Move.from_uci(u)
                    if m not in board.legal_moves: raise ValueError()
                    board.push(m)
                return main
        except (ValueError, TypeError):
            pass
        return legal_first_variation(r['normalized_fen'],r['tree_json'])


def flatten_source_tree(fen: str, tree_json: str | None, max_nodes=3500, max_depth=150):
    """Return every stored variation as navigable nodes with source comments and FEN.

    Null-move branches and impossible moves are visible but blocked; no invented board states.
    """
    root_board=chess.Board(fen)
    if not root_board.is_valid():
        raise ValueError('Некоректний FEN')
    try:
        roots=json.loads(tree_json or '{}').get('variations', [])
    except (ValueError,TypeError,AttributeError) as exc:
        raise ValueError('Неможливо прочитати дерево варіантів CDB') from exc
    nodes=[{'id':0,'parent':None,'fen':root_board.fen(),'label':'Початкова позиція',
            'uci':None,'san':None,'comment':'','starting_comment':'','nags':[],
            'playable':True,'children':[]}]
    truncated=False
    def walk_blocked(children, parent, depth):
        """Preserve the structure under an ambiguous null/invalid move without inventing FEN."""
        nonlocal truncated
        if depth >= max_depth:
            truncated=True;return
        for source in children or []:
            if len(nodes)>=max_nodes:
                truncated=True;return
            if not isinstance(source,dict):continue
            u=source.get('uci') or ''
            n={'id':len(nodes),'parent':parent,'fen':None,
               'label':source.get('san') or u or '(без ходу)',
               'san':source.get('san'),'uci':u,
               'comment':source.get('comment') or '',
               'starting_comment':source.get('starting_comment') or '',
               'nags':source.get('nags') or [],'playable':False,
               'blocked_reason':'Неможливо встановити позицію після попереднього умовного або нелегального ходу',
               'children':[]}
            nodes.append(n);nodes[parent]['children'].append(n['id'])
            walk_blocked(source.get('children',[]),n['id'],depth+1)

    def walk(children, parent, board, depth):
        nonlocal truncated
        if depth>=max_depth:
            truncated=True;return
        for source in children or []:
            if len(nodes)>=max_nodes:
                truncated=True;return
            if not isinstance(source,dict):continue
            u=source.get('uci') or ''
            special=u=='0000'
            playable=False; note=''; next_board=None
            if not special:
                try:
                    move=chess.Move.from_uci(u)
                    if move in board.legal_moves:
                        next_board=board.copy(stack=False)
                        san=board.san(move)
                        next_board.push(move)
                        playable=True
                    else: note='Хід нелегальний для цієї позиції'
                except (TypeError,ValueError):note='Некоректний запис ходу'
            else:note='Позначка -- / 0000: умовний хід; її не можна відтворити як переміщення фігури'
            n={'id':len(nodes),'parent':parent,'fen':next_board.fen() if playable else None,
               'label':((f'{board.fullmove_number}.' if board.turn else f'{board.fullmove_number}...')
                        +(san if playable else (source.get('san') or u))),
               'san':source.get('san') or (san if playable else None),'uci':u,
               'comment':source.get('comment') or '',
               'starting_comment':source.get('starting_comment') or '',
               'nags':source.get('nags') or [],'playable':playable,
               'blocked_reason':note,'children':[]}
            nodes.append(n)
            nodes[parent]['children'].append(n['id'])
            if playable:
                walk(source.get('children',[]), n['id'], next_board, depth+1)
            elif source.get('children'):
                n['blocked_reason']+='; подальші вузли показано без обчислення позиції'
                walk_blocked(source.get('children',[]), n['id'], depth+1)
    walk(roots,0,root_board,0)
    return {'nodes':nodes,'total_nodes':len(nodes),'truncated':truncated,
            'root_variations':len(nodes[0]['children']),
            'blocked_nodes':sum(not n['playable'] for n in nodes[1:]),
            'note':'Повне дерево до зазначеного ліміту. Коментарі й оцінки NAG взяті з джерела; -- не є легальним ходом.'}


def session_tree(db,uid,sid):
    with connect(db) as c:
        r=c.execute('''SELECT e.id exercise_id,e.starting_fen,r.tree_json,r.original_id,s.filename
            FROM exercise_sessions es
            JOIN cdb_exercises e ON e.id=es.exercise_id
            JOIN cdb_records r ON r.id=e.record_id JOIN cdb_sources s ON s.id=r.source_id
            WHERE es.id=? AND es.user_id=?''',(sid,uid)).fetchone()
        if not r:raise LookupError('Сесія не знайдена')
        ret=flatten_source_tree(r['starting_fen'],r['tree_json'])
        ret.update({'exercise_id':r['exercise_id'],'source':r['filename'],'source_record_id':r['original_id']})
        return ret


def main():
    p=argparse.ArgumentParser(description='MVP 0.5: non-destructive expansion of existing imported CDB catalogue')
    p.add_argument('--db',required=True)
    p.add_argument('--out')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    r=expand_sources(a.db,dry_run=a.dry_run)
    text=json.dumps(r,ensure_ascii=False,indent=2)
    print(text)
    if a.out:Path(a.out).write_text(text,encoding='utf-8')

if __name__=='__main__':main()
