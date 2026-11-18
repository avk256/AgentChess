import os, sqlite3, json, hashlib, secrets, datetime, io, csv, subprocess
from pathlib import Path
from contextlib import contextmanager
import chess, chess.pgn, chess.engine
from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from passlib.hash import pbkdf2_sha256

ROOT=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('AGENTCHESS_DATA',str(ROOT/'data'))); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'agentchess.sqlite3'; ENGINE=os.environ.get('STOCKFISH_PATH','/usr/games/stockfish')
app=FastAPI(title='AgentChess MVP',version='0.5.11')

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT DEFAULT 'student',token TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY,name TEXT UNIQUE,sha256 TEXT UNIQUE,records INTEGER DEFAULT 0,report TEXT);
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,source_id INTEGER,source_table TEXT,source_row TEXT,fen TEXT,move_text TEXT,raw TEXT,status TEXT,topic TEXT,difficulty INTEGER DEFAULT 1,solution TEXT,FOREIGN KEY(source_id) REFERENCES sources(id));
CREATE INDEX IF NOT EXISTS idx_records_topic ON records(topic,status);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,user_id INTEGER,record_id INTEGER,fen TEXT,topic TEXT,move TEXT,correct INTEGER,created TEXT);
CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY,user_id INTEGER,fen TEXT,start_fen TEXT,moves TEXT,skill INTEGER,status TEXT,created TEXT);
''')
init()

class Auth(BaseModel): username:str; password:str
class Move(BaseModel): move:str
class NewGame(BaseModel): fen:str|None=None; skill:int=4; color:str='white'
class Attempt(BaseModel): session_id:str; move:str

def user(authorization:str|None):
 token=(authorization or '').removeprefix('Bearer ').strip()
 with conn() as c: r=c.execute('SELECT id,username,role FROM users WHERE token=?',(token,)).fetchone()
 if not r: raise HTTPException(401,'Увійдіть в акаунт')
 return dict(r)

def board_of(fen):
 try:
  b=chess.Board(fen)
  if not b.is_valid(): raise ValueError('Invalid position')
  return b
 except Exception: raise HTTPException(422,'Некоректний FEN')

def apply(b,move):
 try: m=b.parse_uci(move)
 except ValueError:
  try: m=b.parse_san(move)
  except ValueError: raise HTTPException(422,'Нелегальний хід')
 b.push(m); return m

def engine_move(b,skill):
 if not Path(ENGINE).exists(): raise HTTPException(503,'Stockfish не встановлено: '+ENGINE)
 with chess.engine.SimpleEngine.popen_uci(ENGINE,timeout=15) as e:
  e.configure({'Skill Level':max(0,min(20,skill))})
  return e.play(b,chess.engine.Limit(time=.12)).move

def gamestate(r):
 b=chess.Board(r['start_fen']);
 for u in json.loads(r['moves']): b.push_uci(u)
 return b

@app.get('/api/position/status')
def position_status(fen:str):
 """Authoritative checkmate status for any board view, independent of CDB metadata."""
 if fen=='start':fen=chess.STARTING_FEN
 if len(fen)>120:raise HTTPException(422,'Некоректний FEN')
 board=board_of(fen)
 mate=board.is_checkmate()
 king=board.king(board.turn) if mate else None
 return {'is_checkmate':mate,'king_square':chess.square_name(king) if king is not None else None}

@app.post('/api/auth/register')
def register(a:Auth):
 if len(a.username)<3 or len(a.password)<8: raise HTTPException(422,'Логін ≥3, пароль ≥8 символів')
 token=secrets.token_urlsafe(32)
 try:
  with conn() as c: c.execute('INSERT INTO users(username,password,token,role) VALUES(?,?,?,?)',(a.username,pbkdf2_sha256.hash(a.password),token,'admin' if a.username==os.environ.get('AGENTCHESS_BOOTSTRAP_ADMIN','') and os.environ.get('AGENTCHESS_BOOTSTRAP_ADMIN') else 'student'))
 except sqlite3.IntegrityError: raise HTTPException(409,'Логін зайнятий')
 return {'token':token,'username':a.username}
@app.post('/api/auth/login')
def login(a:Auth):
 with conn() as c: r=c.execute('SELECT * FROM users WHERE username=?',(a.username,)).fetchone()
 if not r or not pbkdf2_sha256.verify(a.password,r['password']): raise HTTPException(401,'Неправильні дані')
 token=secrets.token_urlsafe(32)
 with conn() as c: c.execute('UPDATE users SET token=? WHERE id=?',(token,r['id']))
 return {'token':token,'username':a.username}
@app.get('/api/users/me')
def me(authorization:str|None=Header(None)): return user(authorization)

from catalog import init_catalog, import_path as catalog_import_path, catalog_query, connect as catalog_connect, CHESS_AVAILABLE
import tempfile
init_catalog(DB)
from exercise041 import init_exercises041, available_counts, start_session, make_move, hint, catalog_solution
init_exercises041(DB)
from exercise042 import session_solution, reset_user_progress

from exercise05 import session_tree, flatten_source_tree
from exercise055 import reset_current_exercise, topic_sources, comment_for_line
from exercise053 import authored_moves
from stockfish053 import init_stockfish053, timeline, engine_selfplay, save_solution
init_stockfish053(DB)

def _position_annotation(session_id, user_id, index=None):
    with conn() as c:
        row=c.execute("""SELECT s.line_index,r.movetext,r.tree_json,r.mainline_json
             FROM exercise_sessions s JOIN cdb_exercises e ON e.id=s.exercise_id
             JOIN cdb_records r ON r.id=e.record_id
             WHERE s.id=? AND s.user_id=?""",(session_id,user_id)).fetchone()
    if not row:return ''
    return comment_for_line(row['movetext'],row['tree_json'],row['mainline_json'],
                            row['line_index'] if index is None else index)

class ResetCurrentExercise(BaseModel):
    session_id:str

@app.post('/api/exercises/reset-current')
def reset_one_exercise(a:ResetCurrentExercise,authorization:str|None=Header(None)):
    u=user(authorization)
    try:
        result=reset_current_exercise(DB,u['id'],a.session_id)
    except LookupError as exc:raise HTTPException(404,str(exc))
    with conn() as c:
        r=c.execute("""SELECT e.topic,e.starting_fen,e.readiness,e.validation_method,e.answer_uci,
                   r.mainline_json,r.tree_json
                   FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id
                   WHERE e.id=?""",(result['exercise_id'],)).fetchone()
    from exercise04 import _session_kind, _line, _description
    line=_line(r)
    kind=_session_kind(r,line)
    if kind=='VERIFIED' and r['validation_method']=='STOCKFISH_TOP1_GAP' and len(line)>1:
        kind='SOURCE_LINE'
    with conn() as c:
        c.execute('UPDATE exercise_sessions SET session_type=? WHERE id=?',
                  (kind,a.session_id))
    result.update({'mode':kind,'goal':_description(result['topic'],kind,result['mate_in']),
                   'side':'white' if result['fen'].split()[1]=='w' else 'black',
                   'comment':_position_annotation(a.session_id,u['id'],0)})
    return result

@app.get('/api/exercises/topic-sources')
def exercise_topic_sources(authorization:str|None=Header(None)):
    user(authorization)
    return topic_sources(DB)


@app.get('/api/exercises/{session_id}/tree')
def exercise_variation_tree(session_id:str, authorization:str|None=Header(None)):
 u=user(authorization)
 try:return session_tree(DB,u['id'],session_id)
 except LookupError as exc:raise HTTPException(404,str(exc))
 except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/catalog/{rid}/tree')
def catalog_variation_tree(rid:int, authorization:str|None=Header(None)):
 user(authorization)
 with conn() as c:
  r=c.execute('SELECT normalized_fen,tree_json,original_id FROM cdb_records WHERE id=?',(rid,)).fetchone()
 if not r:raise HTTPException(404,'Запис не знайдено')
 if not r['normalized_fen']:raise HTTPException(422,'У джерелі немає коректного FEN')
 try:return flatten_source_tree(r['normalized_fen'],r['tree_json'])
 except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/exercises/{session_id}/solution')
def view_session_solution(session_id:str, authorization:str|None=Header(None)):
 u=user(authorization)
 try:return session_solution(DB,u['id'],session_id)
 except LookupError as exc:raise HTTPException(404,str(exc))

class ResetProgress(BaseModel):
 confirmation:str
 include_games:bool=True

@app.post('/api/progress/reset')
def reset_progress(a:ResetProgress,authorization:str|None=Header(None)):
 u=user(authorization)
 if a.confirmation!='СКИНУТИ':
  raise HTTPException(422,'Для підтвердження введіть СКИНУТИ')
 result=reset_user_progress(DB,u['id'],a.include_games)
 with conn() as c:
  n=c.execute('SELECT COUNT(*) FROM stockfish_solutions WHERE user_id=?',(u['id'],)).fetchone()[0]
  c.execute('DELETE FROM stockfish_solutions WHERE user_id=?',(u['id'],))
 result.setdefault('deleted',{})['stockfish_solutions']=n
 return result

@app.get('/api/exercises/source-usage')
def source_usage(authorization:str|None=Header(None)):
 user(authorization)
 with conn() as c:
  rows=[dict(r) for r in c.execute('''SELECT s.filename,s.level,s.games_count,
              COUNT(e.id) exercises FROM cdb_sources s
              LEFT JOIN cdb_records r ON r.source_id=s.id
              LEFT JOIN cdb_exercises e ON e.record_id=r.id
              GROUP BY s.id ORDER BY exercises DESC,s.filename''')]
 return {'imported_sources':len(rows), 'used_sources':sum(r['exercises']>0 for r in rows),
         'total_exercises':sum(r['exercises'] for r in rows), 'sources':rows}

@app.post('/api/imports')
async def upload(file:UploadFile=File(...),authorization:str|None=Header(None)):
 u=user(authorization)
 if u['role']!='admin': raise HTTPException(403,'Лише адміністратор може імпортувати')
 if not (file.filename.lower().endswith('.cdb') or file.filename.lower().endswith(('.tar.gz','.tgz'))):
  raise HTTPException(422,'Потрібен .cdb або .tar.gz')
 data=await file.read(60*1024*1024+1)
 if len(data)>60*1024*1024:raise HTTPException(413,'Архів перевищує 60 МБ')
 with tempfile.TemporaryDirectory() as td:
  path=Path(td)/Path(file.filename).name
  path.write_bytes(data)
  return catalog_import_path(DB,path,DATA/'converted')

@app.get('/api/sources')
def sources(authorization:str|None=Header(None)):
 user(authorization)
 with catalog_connect(DB) as c:
  return [dict(r) for r in c.execute('SELECT id,filename,title,level,games_count,chapters_count FROM cdb_sources ORDER BY filename')]

@app.get('/api/sources/{sid}')
def source_detail(sid:int,authorization:str|None=Header(None)):
 user(authorization)
 with catalog_connect(DB) as c:
  src=c.execute('SELECT * FROM cdb_sources WHERE id=?',(sid,)).fetchone()
  if not src:raise HTTPException(404,'Джерело не знайдене')
  chapters=[dict(r) for r in c.execute('SELECT original_id,parent_original_id,start_game_id,title FROM cdb_chapters WHERE source_id=? ORDER BY original_id',(sid,))]
  return {'source':dict(src),'chapters':chapters}

@app.get('/api/exercises/catalog/sources')
def exercise_catalog_sources_api(topic:str|None=None,authorization:str|None=Header(None)):
 user(authorization)
 from catalog import exercise_catalog_sources
 return exercise_catalog_sources(DB,topic)

@app.get('/api/exercises/catalog/numbers')
def exercise_catalog_numbers_api(topic:str,source_id:int,authorization:str|None=Header(None)):
 user(authorization)
 from catalog import exercise_catalog_numbers
 return exercise_catalog_numbers(DB,topic,source_id)

@app.get('/api/exercises/catalog')
def exercise_catalog(topic:str|None=None,source_id:int|None=None,original_id:int|None=None,
                     limit:int=20,offset:int=0,authorization:str|None=Header(None)):
 user(authorization)
 from catalog import exercise_catalog_query
 return exercise_catalog_query(DB,topic,limit,offset,source_id,original_id)

@app.get('/api/catalog')
def catalog(topic:str|None=None,status:str|None=None,source_id:int|None=None,
            record_type:str|None=None,difficulty:int|None=None,limit:int=50,offset:int=0,
            original_id:int|None=None,include_book_text:bool=False,
            authorization:str|None=Header(None)):
 user(authorization)
 # Compatibility with old clients. Source/number filters must still use
 # the authoritative cdb_exercises.topic when searching training material.
 if topic is not None and not any(x is not None for x in (status,record_type,difficulty)) and not include_book_text:
  from catalog import exercise_catalog_query
  return exercise_catalog_query(DB,topic,limit,offset,source_id,original_id)
 result=catalog_query(DB,topic,status,source_id,record_type,difficulty,limit,offset,include_book_text)
 if original_id is not None:
  # For an unthemed raw record lookup, restrict before pagination with SQL
  # in a dedicated parameterized query rather than filtering paged results.
  with catalog_connect(DB) as c:
   clauses=['r.original_id=?'];args=[original_id]
   if source_id is not None:clauses.append('r.source_id=?');args.append(source_id)
   if topic is not None:clauses.append('r.topic=?');args.append(topic)
   where=' AND '.join(clauses)
   result['total']=c.execute('SELECT COUNT(*) FROM cdb_records r WHERE '+where,args).fetchone()[0]
   items=c.execute("""SELECT r.id,r.source_id,s.filename,r.original_id,r.event,
      r.normalized_fen AS fen,r.record_type,r.topic,r.mate_in,r.elo,r.difficulty,r.status
      FROM cdb_records r JOIN cdb_sources s ON s.id=r.source_id WHERE """+where+
      ' ORDER BY r.id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
   result['items']=[dict(x) for x in items]
 return result

@app.get('/api/catalog/{rid}')
def catalog_record(rid:int,authorization:str|None=Header(None)):
 user(authorization)
 with catalog_connect(DB) as c:
  r=c.execute('SELECT * FROM cdb_records WHERE id=?',(rid,)).fetchone()
  if not r:raise HTTPException(404,'Запис не знайдено')
  obj=dict(r)
  for k in ('raw_json','mainline_json','tree_json','errors_json'):
   obj[k.removesuffix('_json')]=json.loads(obj.pop(k) or 'null')
  # Only authorized admin sees full original solution tree; clients cannot leak answer
  if user(authorization)['role']!='admin':
   obj.pop('tree',None);obj.pop('mainline',None);obj.pop('normalized_pgn',None);obj.pop('movetext',None);obj.pop('raw',None);obj.pop('errors',None);obj.pop('normalized_movetext',None)
  return obj

@app.get('/api/catalog/{rid}/solution')
def source_answer(rid:int,authorization:str|None=Header(None)):
 user(authorization)
 try:return catalog_solution(DB,rid)
 except LookupError as exc:raise HTTPException(404,str(exc))

@app.get('/api/imports/{run_id}/report')
def import_report(run_id:int,authorization:str|None=Header(None)):
 u=user(authorization)
 if u['role']!='admin':raise HTTPException(403,'Лише адміністратор')
 with catalog_connect(DB) as c:r=c.execute('SELECT report_json FROM cdb_import_runs WHERE id=?',(run_id,)).fetchone()
 if not r:raise HTTPException(404,'Звіт не знайдено')
 return json.loads(r['report_json']) if r['report_json'] else {'status':'running'}

@app.get('/api/exercises/topics')
def exercise_topics(authorization:str|None=Header(None)):
 user(authorization)
 return available_counts(DB)

@app.get('/api/exercises/count')
def exercise_count(topic:str='мат',difficulty:int|None=None,mate_in:int|None=None,authorization:str|None=Header(None)):
 user(authorization)
 try:return available_counts(DB,topic,difficulty,mate_in)
 except ValueError as exc:raise HTTPException(422,str(exc))

@app.get('/api/exercises/next')
def next_exercise(topic:str='мат',difficulty:int|None=None,mate_in:int|None=None,authorization:str|None=Header(None)):
 u=user(authorization)
 try:result=start_session(DB,u['id'],topic,difficulty,mate_in)
 except ValueError as exc:raise HTTPException(422,str(exc))
 if result is None:raise HTTPException(404,'У цьому фільтрі немає доступних позицій. Змініть тему або рівень.')
 result['comment']=_position_annotation(result['session_id'],u['id'],0)
 return result

@app.post('/api/exercises/attempt')
def attempt(a:Attempt,authorization:str|None=Header(None)):
 u=user(authorization)
 try:
  result=make_move(DB,u['id'],a.session_id,a.move)
  result['comment']=_position_annotation(a.session_id,u['id'])
  return result
 except LookupError as exc:raise HTTPException(404,str(exc))
 except ValueError as exc:raise HTTPException(422,str(exc))
 except RuntimeError as exc:raise HTTPException(409,str(exc))

class ExerciseHint(BaseModel):session_id:str
@app.post('/api/exercises/hint')
def exercise_hint(a:ExerciseHint,authorization:str|None=Header(None)):
 u=user(authorization)
 try:return hint(DB,u['id'],a.session_id)
 except LookupError as exc:raise HTTPException(404,str(exc))
 except RuntimeError as exc:raise HTTPException(409,str(exc))

class GameFromExercise(BaseModel):
 session_id:str
 skill:int=4
 color:str|None=None

def _turn_color(b):
 return 'white' if b.turn else 'black'

def _start_game(user_id, board, skill, color):
 if color not in ('white','black'):
  raise HTTPException(422,'Оберіть білі або чорні фігури')
 if not 0<=skill<=20:raise HTTPException(422,'Skill Level 0..20')
 if board.is_game_over(claim_draw=True):raise HTTPException(409,'Позиція вже завершена')
 initial=board.fen();moves=[]
 if _turn_color(board)!=color:
  mv=engine_move(board,skill);board.push(mv);moves.append(mv.uci())
 status=board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else 'active'
 with conn() as c:
  cur=c.execute('''INSERT INTO games(user_id,fen,start_fen,moves,skill,status,created,player_color)
     VALUES(?,?,?,?,?,?,?,?)''',(user_id,board.fen(),initial,json.dumps(moves),skill,status,
       datetime.datetime.now(datetime.timezone.utc).isoformat(),color))
  gid=cur.lastrowid
 return {'id':gid,'fen':board.fen(),'skill':skill,'player_color':color,
         'moves':moves,'status':status,'timeline':timeline(initial,moves)}

@app.post('/api/games/from-exercise')
def game_from_exercise(a:GameFromExercise,authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:
  r=c.execute('''SELECT s.current_fen,e.starting_fen FROM exercise_sessions s
      JOIN cdb_exercises e ON e.id=s.exercise_id WHERE s.id=? AND s.user_id=?''',
              (a.session_id,u['id'])).fetchone()
 if not r:raise HTTPException(404,'Вправу не знайдено')
 board=board_of(r['current_fen']);note='Поточна позиція вправи'
 if board.is_game_over(claim_draw=True):
  board=board_of(r['starting_fen']);note='Завершена позиція: повернення до початку вправи'
 # User's pieces are always at the bottom. The chosen color fixes orientation.
 color=a.color or _turn_color(board)
 result=_start_game(u['id'],board,a.skill,color)
 return {**result,'color':color,'from_exercise':a.session_id,'note':note}

@app.post('/api/games')
def new_game(a:NewGame,authorization:str|None=Header(None)):
 u=user(authorization)
 return _start_game(u['id'],board_of(a.fen or chess.STARTING_FEN),a.skill,a.color)

@app.post('/api/games/{gid}/moves')
def game_move(gid:int,a:Move,authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:r=c.execute('SELECT * FROM games WHERE id=? AND user_id=?',(gid,u['id'])).fetchone()
 if not r:raise HTTPException(404,'Партію не знайдено')
 if r['status']!='active':raise HTTPException(409,'Партія завершена')
 b=gamestate(r)
 if _turn_color(b)!=r['player_color']:
  raise HTTPException(409,'Зараз хід Stockfish, а не вашої сторони')
 m=apply(b,a.move);moves=json.loads(r['moves']);moves.append(m.uci());reply=None
 if not b.is_game_over(claim_draw=True):
  reply=engine_move(b,r['skill']);b.push(reply);moves.append(reply.uci())
 status=b.result(claim_draw=True) if b.is_game_over(claim_draw=True) else 'active'
 with conn() as c:c.execute('UPDATE games SET fen=?,moves=?,status=? WHERE id=? AND user_id=?',
                            (b.fen(),json.dumps(moves),status,gid,u['id']))
 return {'fen':b.fen(),'reply':reply.uci() if reply else None,'status':status,
         'moves':moves,'player_color':r['player_color'],
         'timeline':timeline(r['start_fen'],moves)}

@app.post('/api/games/{gid}/flip')
def flip_game(gid:int,authorization:str|None=Header(None)):
 """Switch which colour the person controls; the user's colour stays below.

 If it becomes Stockfish's turn, the engine responds before accepting user input.
 All previous moves remain in the same game history.
 """
 u=user(authorization)
 with conn() as c:r=c.execute('SELECT * FROM games WHERE id=? AND user_id=?',(gid,u['id'])).fetchone()
 if not r:raise HTTPException(404,'Партію не знайдено')
 other='black' if r['player_color']=='white' else 'white'
 b=gamestate(r);moves=json.loads(r['moves']);reply=None
 if r['status']=='active' and _turn_color(b)!=other:
  reply=engine_move(b,r['skill']);b.push(reply);moves.append(reply.uci())
 status=b.result(claim_draw=True) if b.is_game_over(claim_draw=True) else r['status']
 with conn() as c:
  c.execute('UPDATE games SET player_color=?,fen=?,moves=?,status=? WHERE id=? AND user_id=?',
            (other,b.fen(),json.dumps(moves),status,gid,u['id']))
 return {'id':gid,'fen':b.fen(),'player_color':other,'reply':reply.uci() if reply else None,
         'status':status,'timeline':timeline(r['start_fen'],moves)}

@app.get('/api/games/{gid}/timeline')
def game_timeline(gid:int,authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:r=c.execute('SELECT * FROM games WHERE id=? AND user_id=?',(gid,u['id'])).fetchone()
 if not r:raise HTTPException(404,'Партію не знайдено')
 return {'game_id':gid,'player_color':r['player_color'],'status':r['status'],
         'timeline':timeline(r['start_fen'],json.loads(r['moves']))}

@app.get('/api/games/{gid}')
def get_game(gid:int,authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:r=c.execute('SELECT * FROM games WHERE id=? AND user_id=?',(gid,u['id'])).fetchone()
 if not r:raise HTTPException(404,'Партію не знайдено')
 return dict(r)

class SolveWithStockfish(BaseModel):
 session_id:str
 max_plies:int=24
 think_time:float=0.12

@app.post('/api/stockfish/solve')
def stockfish_solve(a:SolveWithStockfish,authorization:str|None=Header(None)):
 """Play BOTH colors from the original CDB position; capped local demonstration."""
 u=user(authorization)
 if not 2<=a.max_plies<=80 or not .05<=a.think_time<=.4:
  raise HTTPException(422,'Дозволено 2–80 півходів та 0.05–0.4 с на хід')
 with conn() as c:
  row=c.execute('''SELECT s.exercise_id,e.starting_fen FROM exercise_sessions s
       JOIN cdb_exercises e ON e.id=s.exercise_id
       WHERE s.id=? AND s.user_id=?''',(a.session_id,u['id'])).fetchone()
 if row is None:raise HTTPException(404,'Вправу не знайдено')
 try:result=engine_selfplay(row['starting_fen'],ENGINE,a.max_plies,a.think_time)
 except FileNotFoundError as exc:raise HTTPException(503,str(exc))
 except ValueError as exc:raise HTTPException(422,str(exc))
 except (chess.engine.EngineError,chess.engine.EngineTerminatedError) as exc:
  raise HTTPException(503,'Stockfish не завершив аналіз: '+str(exc))
 run_id=save_solution(DB,u['id'],row['exercise_id'],row['starting_fen'],result,a.max_plies,a.think_time)
 return {'run_id':run_id,'mode':'engine_vs_engine',**result}

@app.get('/api/stockfish/solutions/{run_id}')
def stockfish_solution(run_id:int,authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:
  r=c.execute('SELECT * FROM stockfish_solutions WHERE id=? AND user_id=?',(run_id,u['id'])).fetchone()
 if r is None:raise HTTPException(404,'Результат не знайдено')
 return {'run_id':run_id,'status':r['status'],
         'timeline':timeline(r['start_fen'],json.loads(r['moves'])),
         'mode':'engine_vs_engine'}

@app.get('/api/exercises/mate-lengths')
def mate_lengths(authorization:str|None=Header(None)):
 user(authorization)
 with conn() as c:
  rows=[{'moves':r['mate_in'],'count':r['n']} for r in c.execute('''SELECT mate_in,COUNT(*) n
       FROM cdb_exercises WHERE topic='мат' GROUP BY mate_in ORDER BY mate_in''')]
 return {'lengths':rows,'rule':'Кількість ходів атакуючої сторони у повній головній лінії CDB'}

@app.get('/api/progress')
def progress(authorization:str|None=Header(None)):
 u=user(authorization)
 with conn() as c:
  attempts=[dict(r) for r in c.execute('SELECT topic,COUNT(*) attempts,SUM(correct) correct FROM attempts WHERE user_id=? GROUP BY topic',(u['id'],))]
  games=[dict(r) for r in c.execute('SELECT status,COUNT(*) count FROM games WHERE user_id=? GROUP BY status',(u['id'],))]
  sessions=[dict(r) for r in c.execute('''SELECT e.topic,COUNT(*) started,SUM(s.finished) completed,
        SUM(s.wrong_attempts) mistakes FROM exercise_sessions s JOIN cdb_exercises e ON e.id=s.exercise_id
        WHERE s.user_id=? GROUP BY e.topic''',(u['id'],))]
 return {'attempts':attempts,'games':games,'exercise_sessions':sessions}
@app.get('/api/health')
def health():return {'status':'ok','stockfish':Path(ENGINE).exists(),'python_chess':CHESS_AVAILABLE,'version':'0.5.5'}
app.mount('/static',StaticFiles(directory=ROOT/'frontend'),name='static')
@app.get('/')
def index():return FileResponse(ROOT/'frontend'/'index.html')
