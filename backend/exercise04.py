"""AgentChess 0.4: full CDB candidate catalogue and transparent exercise sessions.

The source catalogue is trusted for *study*, not for objective uniqueness.  READY
moves retain their earlier validation; other source lines are labelled GUIDED,
and a position without solution becomes an exploratory one-move practice.  No
unverified move is ever claimed to be objectively best.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3

import chess

from exercise03 import TOPICS as OLD_TOPICS, _board, _line as _original_line, connect, init_exercises, mate_ones
from exercise05_topics import NEW_TOPICS
from schema051 import ensure_tree_json_column
TOPICS = tuple(OLD_TOPICS) + tuple(x for x in NEW_TOPICS if x not in OLD_TOPICS)

def _line(row):
    """For added source studies, use a legal tree branch when mainline has a null marker."""
    raw=_original_line(row)
    if raw and all(x!='0000' for x in raw):
        return raw
    try:
        if row['topic'] in NEW_TOPICS:
            from exercise05 import legal_first_variation
            return legal_first_variation(row['starting_fen'], row['tree_json'])
    except (KeyError, IndexError):
        pass
    return raw



def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def init_exercises04(db):
    init_exercises(db)
    ensure_tree_json_column(db)
    with connect(db) as c:
        cols = {r['name'] for r in c.execute('PRAGMA table_info(exercise_sessions)')}
        if 'session_type' not in cols:
            c.execute("ALTER TABLE exercise_sessions ADD COLUMN session_type TEXT")
        if 'hint_count' not in cols:
            c.execute('ALTER TABLE exercise_sessions ADD COLUMN hint_count INTEGER NOT NULL DEFAULT 0')
        c.execute('CREATE INDEX IF NOT EXISTS ex04_mate_filter ON cdb_exercises(topic,mate_in,difficulty)')


def _condition(topic, difficulty=None, mate_in=None):
    if topic not in TOPICS:
        raise ValueError('Невідома тема')
    if difficulty is not None and difficulty not in range(1, 6):
        raise ValueError('Складність повинна бути від 1 до 5')
    if mate_in is not None:
        if topic != 'мат':
            raise ValueError('Фільтр кількості ходів доступний тільки для матових задач')
        if not 0 <= mate_in <= 100:
            raise ValueError('Довжина авторського рішення: від 0 до 100 ходів')
    query = ("WHERE e.topic=? AND e.starting_fen IS NOT NULL AND length(trim(e.starting_fen))>0 "
             "AND NOT (e.starting_fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' "
             "AND COALESCE(r.mainline_json,'[]')='[]')")
    args = [topic]
    if difficulty is not None:
        query += ' AND e.difficulty=?'
        args.append(difficulty)
    if mate_in is not None:
        query += ' AND ' + ('e.mate_in IS NULL' if mate_in == 0 else 'e.mate_in=?')
        if mate_in:
            args.append(mate_in)
    return query, args


def available_counts(db, topic=None, difficulty=None, mate_in=None):
    if topic is None:
        with connect(db) as c:
            topics = [dict(r) for r in c.execute('''SELECT e.topic, COUNT(*) total,
                      SUM(CASE WHEN e.readiness='READY' THEN 1 ELSE 0 END) verified,
                      SUM(CASE WHEN e.readiness!='READY' THEN 1 ELSE 0 END) source_based
                      FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
                      WHERE NOT (e.starting_fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
                         AND COALESCE(r.mainline_json,'[]')='[]')
                      GROUP BY e.topic ORDER BY e.topic''')]
        return {'topics': topics, 'total': sum(x['total'] for x in topics)}
    where, args = _condition(topic, difficulty, mate_in)
    with connect(db) as c:
        r = c.execute(f'''SELECT COUNT(*) total,
               SUM(CASE WHEN e.readiness='READY' THEN 1 ELSE 0 END) verified,
               SUM(CASE WHEN e.readiness!='READY' THEN 1 ELSE 0 END) source_based,
               SUM(CASE WHEN r.mainline_json IS NULL OR r.mainline_json='[]' THEN 1 ELSE 0 END) exploration
               FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id {where}''', args).fetchone()
    return {'topic':topic,'difficulty':difficulty,'mate_in':mate_in,
            'total':int(r['total'] or 0), 'verified':int(r['verified'] or 0),
            'source_based':int(r['source_based'] or 0), 'exploration':int(r['exploration'] or 0)}


def _session_kind(row, line):
    if row['readiness']=='READY' and row['answer_uci'] and row['validation_method'] in ('EXACT_MATE_IN_ONE','STOCKFISH_TOP1_GAP'):
        return 'VERIFIED'
    if line:
        return 'SOURCE_LINE'
    return 'EXPLORE'


def _description(topic, mode, mate_in):
    if topic == 'мат':
        if mate_in in (1,2,3):
            task = f'В авторському рішенні CDB атакуюча сторона робить {mate_in} ' + ('хід.' if mate_in % 10 == 1 and mate_in % 100 != 11 else 'ходи.' if mate_in % 10 in (2,3,4) and mate_in % 100 not in (12,13,14) else 'ходів.') + ' Знайдіть і відтворіть авторську матову ідею.'
        else:
            task = 'Знайдіть матову ідею та дослідіть позицію.'
        if mode == 'SOURCE_LINE': task += ' Розіграйте авторське продовження з CDB.'
        if mode == 'EXPLORE': task += ' Рішення в записі відсутнє: це вільне тренування.'
        return task
    descriptions = {
      'незахищені фігури': 'Знайдіть можливість використати незахищену фігуру суперника.',
      'подвійний удар': 'Знайдіть хід, що створює дві загрози одночасно.',
      'зв’язка': 'Знайдіть або використайте зв’язку фігури суперника.',
      'відкритий напад': 'Знайдіть хід, після якого відкриється лінія атаки іншої фігури.',
      'ендшпіль': 'Знайдіть продовження в ендшпілі та вивчіть авторський варіант.',
      'тактичні комбінації': 'Розіграйте тактичну комбінацію з авторського збірника.',
      'історичні комбінації': 'Вивчіть історичну шахову комбінацію та її варіанти.',
      'дебютні пастки': 'Розіграйте дебютну пастку; перевірте відповіді й коментарі автора.',
      'дебютні принципи': 'Вивчіть дебютну позицію, план та продовження з джерела.',
      'навчальні партії': 'Розіграйте фрагмент партії, звертаючи увагу на авторські пояснення.',
      'стратегія та план': 'Вивчіть стратегічний план та авторську послідовність ходів.',
      'оцінка позиції': 'Оцініть позицію, потім розіграйте авторський приклад.',
      'базові мати': 'Спробуйте поставити мат у базовому закінченні.'
    }
    text=descriptions.get(topic,'Знайдіть продовження.')
    if mode=='SOURCE_LINE': text += ' Відповідь перевіряється за авторською лінією з шахової книги CDB.'
    if mode=='EXPLORE': text += ' У джерелі немає записаних ходів: дослідіть позицію у вільному режимі.'
    if mode=='VERIFIED' and topic not in ('мат','базові мати'):
        text += ' Сильний перший хід підтверджений Stockfish; сам мотив узято з джерела.'
    return text


def start_session(db,user_id,topic,difficulty=None,mate_in=None):
    where,args=_condition(topic,difficulty,mate_in)
    with connect(db) as c:
        sql=f'''SELECT e.id, e.topic, e.difficulty, e.mate_in, e.starting_fen,
                  e.readiness,e.validation_method,e.answer_uci,r.mainline_json,r.tree_json
                  FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id {where}
                  ORDER BY CASE WHEN EXISTS(SELECT 1 FROM exercise_sessions s
                           WHERE s.user_id=? AND s.exercise_id=e.id) THEN 1 ELSE 0 END, RANDOM()'''
        rows=c.execute(sql+' LIMIT 80',args+[user_id]).fetchall()
        chosen=None;b=None
        for r in rows:
            b=_board(r['starting_fen'])
            if b is not None and not b.is_game_over():
                chosen=r;break
        if not chosen:return None
        line=_line(chosen)
        kind=_session_kind(chosen,line)
        sid=secrets.token_urlsafe(24)
        c.execute('''INSERT INTO exercise_sessions
                 (id,user_id,exercise_id,current_fen,created_at,session_type)
                 VALUES(?,?,?,?,?,?)''', (sid,user_id,chosen['id'],b.fen(),now(),kind))
        return {'session_id':sid,'id':chosen['id'],'fen':b.fen(),'topic':topic,
                'difficulty':chosen['difficulty'],'mate_in':chosen['mate_in'],
                'side':'white' if b.turn else 'black', 'mode':kind,
                'verified':kind=='VERIFIED','goal':_description(topic,kind,chosen['mate_in']),
                'attempts':0,'finished':False}


def _load_session(c, user_id, sid):
    return c.execute('''SELECT s.*,e.topic,e.record_id,e.readiness,e.answer_uci,e.validation_method,
          e.starting_fen,e.mate_in,r.mainline_json,r.tree_json FROM exercise_sessions s
          JOIN cdb_exercises e ON e.id=s.exercise_id JOIN cdb_records r ON r.id=e.record_id
          WHERE s.id=? AND s.user_id=?''',(sid,user_id)).fetchone()


def hint(db,user_id,session_id):
    with connect(db) as c:
        r=_load_session(c,user_id,session_id)
        if r is None:raise LookupError('Сесію не знайдено')
        if r['finished']:raise RuntimeError('Вправу завершено')
        b=_board(r['current_fen'])
        if b is None:raise RuntimeError('Пошкоджений FEN')
        kind=r['session_type'] or ('VERIFIED' if r['readiness']=='READY' else 'SOURCE_LINE')
        if kind=='EXPLORE': return {'hint':'Авторської лінії немає. Перевірте шахи, взяття та загрози супернику.'}
        moves=_line(r)
        expected=moves[r['line_index']] if kind=='SOURCE_LINE' and r['line_index']<len(moves) else None
        if kind=='VERIFIED':
            opts=json.loads(r['answer_uci'] or '[]')
            expected=opts[0] if opts else None
        try:
            mv=chess.Move.from_uci(expected)
            if mv not in b.legal_moves:raise ValueError()
            piece=b.piece_at(mv.from_square)
            names={chess.PAWN:'пішака',chess.KNIGHT:'коня',chess.BISHOP:'слона',chess.ROOK:'туру',chess.QUEEN:'ферзя',chess.KING:'короля'}
            text=f"Підказка: розгляньте {names.get(piece.piece_type,'фігуру') if piece else 'фігуру'} на {chess.square_name(mv.from_square)}."
        except (ValueError,TypeError):
            text='Перевірте можливі шахи, взяття та загрози.'
        c.execute('UPDATE exercise_sessions SET hint_count=hint_count+1 WHERE id=?',(session_id,))
        return {'hint':text}


def make_move(db,user_id,session_id,move_text):
    with connect(db) as c:
        r=_load_session(c,user_id,session_id)
        if r is None:raise LookupError('Сесію не знайдено')
        if r['finished']:raise RuntimeError('Вправу вже завершено')
        b=_board(r['current_fen'])
        if b is None:raise RuntimeError('Пошкоджений FEN')
        try: move=b.parse_uci(move_text)
        except ValueError:
            try:move=b.parse_san(move_text)
            except ValueError:raise ValueError('Нелегальний хід')
        kind=r['session_type'] or ('VERIFIED' if r['readiness']=='READY' else 'SOURCE_LINE')
        line=_line(r); index=r['line_index']; moves=[]
        if kind=='EXPLORE':
            correct=None
        else:
            expected=json.loads(r['answer_uci'] or '[]') if kind=='VERIFIED' else ([line[index]] if index<len(line) else [])
            correct=move.uci() in expected
        # A legal checkmate solves a mate exercise even when CDB omits this variation.
        # This is a rules-based check on the ACTUAL board, not a string match.
        is_legal_mate=False
        if r['topic']=='мат':
            after_move=b.copy();after_move.push(move)
            is_legal_mate=after_move.is_checkmate()
            if is_legal_mate:correct=True
        new_errors=r['wrong_attempts']+(1 if correct is False else 0)
        c.execute('''INSERT INTO attempts(user_id,record_id,fen,topic,move,correct,created)
                     VALUES(?,?,?,?,?,?,?)''',
                  (user_id,r['record_id'],b.fen(),r['topic'],move.uci(),None if correct is None else int(correct),now()))
        if correct is False:
            c.execute('UPDATE exercise_sessions SET wrong_attempts=? WHERE id=?',(new_errors,session_id))
            return {'correct':False,'finished':False,'fen':b.fen(),'attempts':new_errors,
                    'message':('Цей хід відрізняється від авторського варіанта. Спробуйте інший або скористайтеся підказкою.'
                               if kind=='SOURCE_LINE' else 'Спробуйте знайти інший хід.')}
        b.push(move); index+=1
        if not is_legal_mate and kind=='SOURCE_LINE' and index<len(line):
            try:
                auto=chess.Move.from_uci(line[index])
                if auto in b.legal_moves:
                    moves.append({'uci':auto.uci(),'san':b.san(auto)})
                    b.push(auto);index+=1
            except ValueError:pass
        finished=is_legal_mate or kind in ('VERIFIED','EXPLORE') or index>=len(line) or b.is_game_over()
        c.execute('''UPDATE exercise_sessions SET current_fen=?,line_index=?,wrong_attempts=?,
                     finished=?,finished_at=? WHERE id=?''',
                  (b.fen(),index,new_errors,int(finished),now() if finished else None,session_id))
        message=('Мат підтверджено за правилами шахів (python-chess).' if is_legal_mate else
                 'Авторську лінію пройдено, але мату в цій позиції немає.' if r['topic']=='мат' and finished and not b.is_checkmate() else
                 'Хід виконано. Це дослідницька вправа без еталонного рішення.' if kind=='EXPLORE' else
                 'Авторський варіант пройдено.' if kind=='SOURCE_LINE' and finished else
                 'Хід підтверджено.' if kind=='VERIFIED' else 'Продовжуйте авторський варіант.')
        return {'correct':correct,'finished':finished,'fen':b.fen(),'attempts':new_errors,
                'opponent_moves':moves,'is_checkmate':b.is_checkmate(),'message':message}
