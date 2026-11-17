"""AgentChess 0.3: conservative validation and stateful interactive chess exercises.

READY: certified mate-in-one (all legal mate moves) OR source move agrees with
Stockfish top move and has an evaluation gap (engine-assisted tactical exercise).
GUIDED: teach source endgame line; NOT an objective proof of the outcome.
No source solution is exposed to the student before solving.
"""
from __future__ import annotations
import datetime as dt
import json
import secrets
import sqlite3
from collections import Counter
from pathlib import Path

import chess
import chess.engine

TOPICS = ('незахищені фігури', 'подвійний удар', 'зв’язка', 'відкритий напад', 'мат', 'ендшпіль', 'базові мати')

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def connect(db):
    c = sqlite3.connect(str(db), timeout=60)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=60000')
    return c

def init_exercises(db):
    with connect(db) as c:
        existing = {r['name'] for r in c.execute('PRAGMA table_info(cdb_exercises)')}
        for column, kind in [('validation_json','TEXT'), ('answer_uci','TEXT'), ('validation_method','TEXT'), ('verified_at','TEXT')]:
            if column not in existing:
                c.execute(f'ALTER TABLE cdb_exercises ADD COLUMN {column} {kind}')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS exercise_sessions (
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          exercise_id INTEGER NOT NULL REFERENCES cdb_exercises(id) ON DELETE CASCADE,
          current_fen TEXT NOT NULL, line_index INTEGER NOT NULL DEFAULT 0,
          wrong_attempts INTEGER NOT NULL DEFAULT 0, finished INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ex_session_user ON exercise_sessions(user_id,finished);
        CREATE INDEX IF NOT EXISTS ex_ready_topic ON cdb_exercises(topic,readiness,difficulty);
        ''')

def _board(fen):
    try:
        b = chess.Board(fen)
        return b if b.is_valid() else None
    except (ValueError, TypeError):
        return None

def mate_ones(board):
    result = []
    for m in list(board.legal_moves):
        board.push(m)
        if board.is_checkmate(): result.append(m.uci())
        board.pop()
    return result

def _line(row):
    try: return json.loads(row['mainline_json'] or '[]')
    except (TypeError, json.JSONDecodeError): return []

def _eval_cp(info, turn):
    score = info['score'].pov(turn)
    return score.score(mate_score=10000)

def assess(row, engine=None, think_time=.12, min_gap=90):
    """Return strict validation status and metadata; never guess a chess solution."""
    b = _board(row['starting_fen'])
    base = {'readiness':'REVIEW_REQUIRED', 'review_reason':'Потрібна додаткова шахова перевірка',
            'answer_uci':None, 'validation_method':None, 'validation':{}}
    if b is None or row['status'] != 'LEGAL_MOVES':
        base['review_reason'] = 'Непридатний FEN або статус ходів'
        return base
    line = _line(row)
    if not line:
        base['review_reason'] = 'Відсутня послідовність ходів'
        return base
    try: first = chess.Move.from_uci(line[0])
    except ValueError: return base
    if first not in b.legal_moves:
        base['review_reason'] = 'Перший хід джерела нелегальний'
        return base
    topic = row['topic']
    mates = mate_ones(b)
    if topic in ('мат', 'базові мати') and (row['mate_in'] == 1 or len(line) == 1):
        if mates and first.uci() in mates:
            return {**base,'readiness':'READY','review_reason':None,'answer_uci':json.dumps(mates),
                    'validation_method':'EXACT_MATE_IN_ONE',
                    'validation':{'all_mate_moves':len(mates), 'reference_move':first.uci()}}
        base['review_reason']='Не підтверджено мат за один хід'
        return base
    if topic == 'ендшпіль':
        # Historical instructive lines may be non-optimal. Teach them as a guided study,
        # not as a proven winning endgame.
        if len(line) >= 2:
            test=b.copy()
            for u in line:
                try:
                    move=chess.Move.from_uci(u)
                    if move not in test.legal_moves: return base
                    test.push(move)
                except (ValueError,TypeError): return base
            return {**base,'readiness':'GUIDED','review_reason':None,
                    'answer_uci':json.dumps([line[0]]), 'validation_method':'SOURCE_LINE_STUDY',
                    'validation':{'plies':len(line), 'objective_verified':False}}
        base['review_reason']='Недостатньо ходів для навчального варіанта'
        return base
    if topic in ('мат', 'базові мати'):
        # Multi-move mates are NOT proofed: guide historical line only.
        if len(line) >= 2:
            return {**base, 'readiness':'GUIDED','review_reason':None,
                    'answer_uci':json.dumps([line[0]]),'validation_method':'SOURCE_LINE_STUDY',
                    'validation':{'plies':len(line),'objective_verified':False}}
        return base
    if topic not in ('незахищені фігури','подвійний удар','зв’язка','відкритий напад'):
        base['review_reason']='Тема поки не підтримує автоматичну предметну валідацію'
        return base
    if engine is None:
        base['review_reason']='Для тактичної перевірки потрібен Stockfish'
        return base
    try:
        infos=engine.analyse(b,chess.engine.Limit(time=think_time),multipv=2)
        if len(infos)<2 or not all(inf.get('pv') for inf in infos[:2]):
            base['review_reason']='Stockfish не повернув дві оцінені лінії'; return base
        best=infos[0]['pv'][0]
        best_cp=_eval_cp(infos[0],b.turn)
        next_cp=_eval_cp(infos[1],b.turn)
        gap=best_cp-next_cp
        if best == first and gap >= min_gap and best_cp >= 80:
            return {**base,'readiness':'READY','review_reason':None,'answer_uci':json.dumps([best.uci()]),
                    'validation_method':'STOCKFISH_TOP1_GAP',
                    'validation':{'best_cp':best_cp,'second_cp':next_cp,'gap_cp':gap,
                                  'min_gap_cp':min_gap,'think_time':think_time,
                                  'theme_confirmed_by':'CDB source label',
                                  'note':'Engine agrees on strongest first move, but motif is source-labelled.'}}
        # The CDB move remains teachable as a clearly marked source-line exercise.
        # Do not call it engine-verified or objectively best.
        return {**base,'readiness':'GUIDED','review_reason':None,
                'answer_uci':json.dumps([line[0]]),'validation_method':'SOURCE_LINE_STUDY',
                'validation':{'plies':len(line),'objective_verified':False,
                              'engine_best':best.uci(),'engine_gap_cp':gap}}

    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, ValueError, KeyError) as exc:
        base['review_reason']=f'Помилка перевірки Stockfish: {exc}'
        return base

def validate_catalog(db, engine_path='/usr/games/stockfish', topics=None, limit_per_topic=150,
                     think_time=.12, min_gap=90, reset=False):
    """Validate a bounded batch per topic. Re-running selects unreviewed before READY.

    Set limit_per_topic=0 for every candidate in selected topics.
    """
    init_exercises(db)
    topics = topics or list(TOPICS)
    invalid=set(topics)-set(TOPICS)
    if invalid: raise ValueError(f'Невідомі теми: {invalid}')
    counts=Counter(); engine=None
    needs_engine=any(x in ('незахищені фігури','подвійний удар','зв’язка','відкритий напад') for x in topics)
    if needs_engine:
        if not Path(engine_path).is_file():
            raise FileNotFoundError(f'Не знайдено Stockfish: {engine_path}')
        engine=chess.engine.SimpleEngine.popen_uci(engine_path,timeout=25)
    try:
        for topic in topics:
            with connect(db) as c:
                if reset:
                    c.execute("UPDATE cdb_exercises SET readiness='REVIEW_REQUIRED',validation_json=NULL,answer_uci=NULL,validation_method=NULL,verified_at=NULL WHERE topic=?",(topic,))
                sql='''SELECT e.id,e.starting_fen,e.topic,e.mate_in,r.status,r.mainline_json
                    FROM cdb_exercises e JOIN cdb_records r ON e.record_id=r.id
                    WHERE e.topic=? AND e.readiness='REVIEW_REQUIRED' AND e.verified_at IS NULL
                    ORDER BY e.id'''
                if limit_per_topic > 0: sql += ' LIMIT '+str(int(limit_per_topic))
                rows=[dict(r) for r in c.execute(sql,(topic,))]
            for row in rows:
                outcome=assess(row,engine,think_time,min_gap)
                with connect(db) as c:
                    c.execute('''UPDATE cdb_exercises SET readiness=?,review_reason=?,answer_uci=?,
                      validation_method=?,validation_json=?,verified_at=? WHERE id=?''',
                      (outcome['readiness'],outcome['review_reason'],outcome['answer_uci'],
                       outcome['validation_method'],json.dumps(outcome['validation'],ensure_ascii=False),
                       now(),row['id']))
                counts[(topic,outcome['readiness'])]+=1
        with connect(db) as c:
            totals=[dict(r) for r in c.execute('''SELECT topic,readiness,COUNT(*) count FROM cdb_exercises
                                      GROUP BY topic,readiness ORDER BY topic,readiness''')]
        return {'processed':[{'topic':k[0],'readiness':k[1],'count':v} for k,v in sorted(counts.items())],
                'totals':totals,'engine':engine_path if needs_engine else None,
                'note':'READY tactic: agreement with Stockfish on first move; motif from CDB label. GUIDED endgame: source-line study, not verified win.'}
    finally:
        if engine: engine.quit()

def topic_counts(db):
    with connect(db) as c:
        return [dict(r) for r in c.execute('''SELECT topic,readiness,COUNT(*) count FROM cdb_exercises
                                             GROUP BY topic,readiness ORDER BY topic,readiness''')]

def start_session(db,user_id,topic,difficulty=None):
    if topic not in TOPICS: raise ValueError('Невідома тема')
    with connect(db) as c:
        sql='''SELECT e.id,e.topic,e.difficulty,e.mate_in,e.starting_fen,e.readiness,e.validation_method,
                e.answer_uci FROM cdb_exercises e
                WHERE e.topic=? AND e.readiness IN ('READY','GUIDED') AND e.answer_uci IS NOT NULL'''
        args=[topic]
        if difficulty is not None:
            sql+=' AND e.difficulty=?';args.append(difficulty)
        sql+=' ORDER BY CASE WHEN EXISTS (SELECT 1 FROM exercise_sessions s WHERE s.user_id=? AND s.exercise_id=e.id) THEN 1 ELSE 0 END, RANDOM() LIMIT 1'
        args.append(user_id)
        r=c.execute(sql,args).fetchone()
        if not r: return None
        b=_board(r['starting_fen'])
        if b is None: return None
        sid=secrets.token_urlsafe(24)
        c.execute('''INSERT INTO exercise_sessions(id,user_id,exercise_id,current_fen,created_at)
                     VALUES(?,?,?,?,?)''',(sid,user_id,r['id'],b.fen(),now()))
        return {'session_id':sid,'id':r['id'],'fen':b.fen(),'topic':topic,'difficulty':r['difficulty'],
                'side':'white' if b.turn else 'black','mode':'guided' if r['readiness']=='GUIDED' else 'verified',
                'goal':('Мат за один хід' if r['validation_method']=='EXACT_MATE_IN_ONE' else
                        'Пройдіть авторський варіант (навчальний, без доказу оптимальності)' if r['readiness']=='GUIDED' else
                        'Знайдіть сильний хід (перевірено Stockfish)'),
                'attempts':0,'finished':False}

def make_move(db,user_id,session_id,move_text):
    with connect(db) as c:
        r=c.execute('''SELECT s.*,e.topic,e.record_id,e.readiness,e.answer_uci,e.validation_method,
            e.starting_fen,rec.mainline_json
            FROM exercise_sessions s JOIN cdb_exercises e ON e.id=s.exercise_id
            JOIN cdb_records rec ON rec.id=e.record_id
            WHERE s.id=? AND s.user_id=?''',(session_id,user_id)).fetchone()
        if r is None: raise LookupError('Сесію не знайдено')
        if r['finished']: raise RuntimeError('Вправу вже завершено')
        b=_board(r['current_fen'])
        if b is None: raise RuntimeError('Сесію пошкоджено')
        try: move=b.parse_uci(move_text)
        except ValueError:
            try: move=b.parse_san(move_text)
            except ValueError: raise ValueError('Нелегальний хід')
        expected=json.loads(r['answer_uci'])
        line=json.loads(r['mainline_json'] or '[]')
        index=r['line_index']
        if r['readiness']=='GUIDED' and index<len(line): expected=[line[index]]
        correct=move.uci() in expected
        new_errors=r['wrong_attempts']+(0 if correct else 1)
        c.execute('''INSERT INTO attempts(user_id,record_id,fen,topic,move,correct,created)
              VALUES(?,?,?,?,?,?,?)''',(user_id,r['record_id'],b.fen(),r['topic'],move.uci(),int(correct),now()))
        if not correct:
            c.execute('UPDATE exercise_sessions SET wrong_attempts=? WHERE id=?',(new_errors,session_id))
            return {'correct':False,'finished':False,'fen':b.fen(),'attempts':new_errors,
                    'message':'Хід легальний, але не відповідає перевіреному рішенню. Спробуйте ще раз.' if r['readiness']=='READY' else
                              'Цей хід відрізняється від навчального варіанта. Спробуйте ще раз.'}
        b.push(move); index+=1; reply=[]
        if r['readiness']=='GUIDED':
            # Autoplay opponent's next authored reply, but never invent alternatives.
            if index<len(line):
                auto=chess.Move.from_uci(line[index])
                if auto not in b.legal_moves: raise RuntimeError('Авторська відповідь нелегальна')
                reply.append({'uci':auto.uci(),'san':b.san(auto)})
                b.push(auto);index+=1
        finished=(r['readiness']=='READY' or index>=len(line))
        c.execute('''UPDATE exercise_sessions SET current_fen=?,line_index=?,wrong_attempts=?,
          finished=?,finished_at=? WHERE id=?''',
          (b.fen(),index,new_errors,int(finished),now() if finished else None,session_id))
        return {'correct':True,'finished':finished,'fen':b.fen(),'attempts':new_errors,'opponent_moves':reply,
                'message':'Зараховано!'+(' Вправу завершено.' if finished else ' Ваш наступний хід.')}
