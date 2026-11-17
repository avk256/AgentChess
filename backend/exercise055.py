"""AgentChess 0.5.5: source annotations, safe replay, endgame topic correction.

No re-import. All destructive changes are scoped to a single authenticated user's
selected exercise; CDB sources and imported chess records stay immutable.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

ENDGAME_MATE_SOURCES = (
    'two_bishops_mate.ru.cdb',
    'king_rook_mate.ru.cdb',
    'king_queen_mate.ru.cdb',
)
START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


def is_book_text(row):
    """Exclude plain book sections masquerading as a starting chess position.

    Valid FEN-only practice positions away from the standard starting board are
    retained; they may be explored even without any author moves.
    """
    fen = row['starting_fen'] if 'starting_fen' in row.keys() else row['normalized_fen']
    moves = row['mainline_json']
    try:
        has_moves = bool(json.loads(moves or '[]'))
    except (ValueError, TypeError):
        has_moves = False
    return fen == START_FEN and not has_moves


def migrate_endgame_topics(db, dry_run=False):
    """Idempotent classification update, preserves record IDs and user sessions."""
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute('''SELECT e.id,e.topic,r.original_id,s.filename
            FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
            JOIN cdb_sources s ON s.id=r.source_id
            WHERE s.filename IN (?,?,?)''', ENDGAME_MATE_SOURCES).fetchall()
        changes = [r for r in rows if r['topic'] != 'ендшпіль']
        if not dry_run:
            c.executemany('UPDATE cdb_exercises SET topic=? WHERE id=?',
                          [('ендшпіль', x['id']) for x in changes])
            # Keep prior progress counts under the same new visible category;
            # only update topic labels, never remove attempts or sessions.
            has_attempts=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='attempts'").fetchone()
            if has_attempts and 'topic' in {col['name'] for col in c.execute('PRAGMA table_info(attempts)')}:
                c.execute('''UPDATE attempts SET topic='ендшпіль'
                  WHERE topic='базові мати' AND record_id IN (
                     SELECT e.record_id FROM cdb_exercises e
                     JOIN cdb_records r ON r.id=e.record_id
                     JOIN cdb_sources s ON s.id=r.source_id
                     WHERE s.filename IN (?,?,?))''', ENDGAME_MATE_SOURCES)
        per_source = {}
        for r in rows:
            per_source[r['filename']] = per_source.get(r['filename'], 0) + 1
        return {'dry_run': dry_run, 'matching_exercises': len(rows),
                'reclassified': len(changes), 'sources': per_source}


def initial_comment(movetext, tree_json=None):
    """Extract PGN comments preceding the first chess move, not full book chapters."""
    raw = (movetext or '').strip()
    comments=[]
    pos=0
    for _ in range(6):
        match = re.match(r'\s*\{([^{}]*)\}', raw[pos:], re.S)
        if not match: break
        txt = match.group(1).strip().lstrip('+-').strip()
        if txt: comments.append(txt)
        pos += match.end()
    if comments:
        return '\n'.join(comments)[:1600]
    try:
        tree=json.loads(tree_json or '{}')
        roots=tree.get('variations') or []
        if roots and isinstance(roots[0], dict):
            return (roots[0].get('starting_comment') or '').strip().lstrip('+-')[:1600]
    except (ValueError, TypeError, AttributeError):
        pass
    return ''


def comment_for_line(movetext, tree_json, mainline_json, index):
    """Return the annotation of the current mainline node, or initial annotation."""
    if index <= 0:
        return initial_comment(movetext, tree_json)
    try:
        moves=json.loads(mainline_json or '[]')
        roots=json.loads(tree_json or '{}').get('variations') or []
        children=roots
        node=None
        for move in moves[:index]:
            node=next((x for x in children if isinstance(x,dict) and x.get('uci')==move), None)
            if node is None: return ''
            children=node.get('children') or []
        if node:
            return (node.get('comment') or '').strip().lstrip('+-')[:1600]
    except (ValueError, TypeError, AttributeError):
        return ''
    return ''


def reset_current_exercise(db, user_id, sid):
    """Allow repeating a completed exercise without changing the CDB catalog.

    Only sessions/attempts for this user+exercise are reset. Stockfish game
    records remain independent historical games, not solved-task markers.
    """
    with sqlite3.connect(db) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        r=c.execute('''SELECT s.id, s.exercise_id,e.record_id,e.starting_fen,e.topic,
                             e.difficulty,e.mate_in
           FROM exercise_sessions s JOIN cdb_exercises e ON e.id=s.exercise_id
           WHERE s.id=? AND s.user_id=?''',(sid,user_id)).fetchone()
        if not r: raise LookupError('Немає доступної вправи для повторного проходження')
        n=c.execute('SELECT COUNT(*) FROM exercise_sessions WHERE user_id=? AND exercise_id=?',
                    (user_id,r['exercise_id'])).fetchone()[0]
        attempts=c.execute('DELETE FROM attempts WHERE user_id=? AND record_id=?',
                           (user_id,r['record_id'])).rowcount
        c.execute('DELETE FROM exercise_sessions WHERE user_id=? AND exercise_id=? AND id<>?',
                  (user_id,r['exercise_id'],sid))
        c.execute('''UPDATE exercise_sessions SET current_fen=?,line_index=0,
                     wrong_attempts=0,finished=0,finished_at=NULL,session_type=NULL,
                     hint_count=0 WHERE id=? AND user_id=?''',
                  (r['starting_fen'],sid,user_id))
        return {'session_id':sid,'exercise_id':r['exercise_id'],'fen':r['starting_fen'],
                'topic':r['topic'],'difficulty':r['difficulty'],'mate_in':r['mate_in'],
                'attempts':0,'finished':False,'reset_sessions':n,'removed_attempts':attempts,
                'catalog_untouched':True}


def topic_sources(db, *, selectable=True):
    """Factual thematic use of the live catalog, not source-name heuristics."""
    with sqlite3.connect(db) as c:
        c.row_factory=sqlite3.Row
        raw = c.execute('''SELECT e.topic,s.filename,COUNT(*) n
              FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
              JOIN cdb_sources s ON s.id=r.source_id
              WHERE NOT (e.starting_fen=? AND
                      (r.mainline_json IS NULL OR r.mainline_json='[]'))
              GROUP BY e.topic,s.filename ORDER BY e.topic,s.filename''',(START_FEN,)).fetchall()
    topics={}
    for row in raw:
        key=row['topic']; item=topics.setdefault(key,{'topic':key,'count':0,'sources':[]})
        item['count']+=row['n'];item['sources'].append({'filename':row['filename'],'count':row['n']})
    return {'topics':list(topics.values()),'total':sum(x['count'] for x in topics.values())}
