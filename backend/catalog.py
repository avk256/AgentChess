"""AgentChess MVP 0.2.1: lossless CDB import and comment-safe CDB PGN normalization.

Optional python-chess: unavailability never causes us to falsely label a move verified.
"""
from __future__ import annotations
import csv, hashlib, io, json, os, re, sqlite3, tarfile, time, datetime, pathlib, tempfile
from collections import Counter
from pathlib import Path

try:
    import chess
    import chess.pgn
    CHESS_AVAILABLE = True
except ImportError:
    chess = None
    CHESS_AVAILABLE = False

TOPIC_BY_SOURCE = {
    'enprize':'незахищені фігури', 'double_attack':'подвійний удар',
    'pin.ru':'зв’язка', 'discovered':'відкритий напад',
    'queen_mate':'базові мати', 'rook_mate':'базові мати',
    'bishops_mate':'базові мати', 'endings':'ендшпіль',
    'endgame':'ендшпіль', 'portish':'ендшпіль', 'polgar':'мат',
    'checkmates':'мат', 'dobr_m2':'мат', 'qmoves':'мат',
    'school':'тактика', 'tactics':'тактика', 'traps':'дебют',
}
ELO_RE = re.compile(r'\{\s*Elo\s*:\s*(\d{2,4})\s*\}', re.I)
MATE_RE = re.compile(r'(?:мат(?:\s+в|\s+у)?\s*|mate\s+in\s*)([1-9])\s*(?:ход|move)?', re.I)
TABLE_ALLOW = {'games','contents','params','bookmarks','pzl_stats'}

# Vlasov/CDB PGN dialect: f8/Q, exd8/N+, bxa1/R# -> =Q, =N, =R.
# Restrict to destination ranks 1/8; leave normal slash notation intact.
CDB_PROMOTION = re.compile(r"(?<![A-Za-z0-9_])([a-h](?:x[a-h])?[18])/([QRBN])(?=$|[^A-Za-z0-9_])", re.I)
NORMALIZER_VERSION = '0.2.1-promotions-v1'


def normalize_cdb_movetext(text: str) -> tuple[str, dict]:
    """Normalize chess move tokens, *never* alter {...} / ';' comments.

    Preserve the original MoveText separately for reversibility. Idempotent.
    """
    if not text:
        return text or '', {'promotions_normalized': 0, 'version': NORMALIZER_VERSION}
    segments = []
    code = []
    count = 0
    i = 0
    n = len(text)
    def flush_code():
        nonlocal count
        if code:
            chunk = ''.join(code)
            chunk, k = CDB_PROMOTION.subn(lambda m: f'{m.group(1)}={m.group(2).upper()}', chunk)
            segments.append(chunk)
            count += k
            code.clear()
    while i < n:
        if text[i] == '{':
            flush_code()
            start = i
            depth = 0
            while i < n:
                if text[i] == '{': depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            segments.append(text[start:i])
        elif text[i] == ';':
            flush_code()
            start = i
            while i < n and text[i] not in '\r\n': i += 1
            segments.append(text[start:i])
        else:
            code.append(text[i]);i += 1
    flush_code()
    return ''.join(segments), {'promotions_normalized': count, 'version': NORMALIZER_VERSION}


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def serialize(value):
    if isinstance(value, bytes): return {'__bytes_hex__': value.hex()}
    return value

def classify(source_name, event, movetext):
    name = source_name.lower()
    topic = next((v for k,v in TOPIC_BY_SOURCE.items() if k in name), 'інше')
    event_l = (event or '').lower()
    if 'мат' in event_l and ('ход' in event_l or 'ход' in name): topic = 'мат'
    if any(k in name for k in ['romanovsky','kotov','lysenko','suetin','koblents','brilliant','bondarevsky']):
        topic = 'теорія / партії'
    match = MATE_RE.search(event or '')
    if not match and 'dobr_m2' in name: match = re.match(r'2','2')
    return topic, int(match.group(1)) if match else None

def level(elo, move_count, variations):
    if elo is not None:
        return 1 if elo < 1100 else 2 if elo < 1400 else 3 if elo < 1700 else 4 if elo < 2000 else 5
    return min(5, max(1, (move_count + 1)//3 + (1 if variations > 1 else 0))) if move_count else None

def chess_parse(fen, text):
    """Parse legal SAN move tree; no guessed solution and no misleading VALID statuses."""
    if not CHESS_AVAILABLE:
        return {'fen':fen, 'fen_valid':None, 'status':'PARSER_UNAVAILABLE', 'pgn':None,
                'tree':None,'mainline':[], 'errors':['python-chess не встановлено']}
    errors=[]
    normalized_text, normalization = normalize_cdb_movetext(text)
    try:
        board=chess.Board(fen.strip()) if fen else chess.Board()
        if not board.is_valid():
            return {'fen':fen,'fen_valid':False,'status':'INVALID_FEN','pgn':None,'tree':None,'mainline':[],
                    'errors':['chess.Board.is_valid() повернув False']}
    except (ValueError,TypeError) as exc:
        return {'fen':fen,'fen_valid':False,'status':'INVALID_FEN','pgn':None,'tree':None,'mainline':[], 'errors':[str(exc)]}
    normalized_fen=board.fen()
    if not (text or '').strip():
        return {'fen':normalized_fen,'fen_valid':True,'status':'EMPTY_MOVETEXT', 'pgn':None,'tree':None,'mainline':[], 'errors':[]}
    head = '[Event "AgentChess CDB import"]\n'
    if fen:
        head += '[SetUp "1"]\n[FEN "' + normalized_fen + '"]\n'
    head += '\n'
    try:
        parsed=chess.pgn.read_game(io.StringIO(head + normalized_text + '\n'))
        if not parsed:
            return {'fen':normalized_fen,'fen_valid':True,'status':'PARSE_ERROR','pgn':None,'tree':None,'mainline':[],'errors':['PGN parser повернув None']}
        errors=[str(x) for x in parsed.errors]
        def make_tree(node, depth=0):
            if depth>=200:
                return {'truncated':True,'variations':[]}
            out=[]
            for child in node.variations:
                out.append({'uci':child.move.uci(),'san':node.board().san(child.move),
                            'comment':child.comment, 'starting_comment':child.starting_comment,
                            'nags':sorted(child.nags), 'children':make_tree(child,depth+1)['variations']})
            return {'variations':out}
        tree=make_tree(parsed)
        main=[m.uci() for m in parsed.mainline_moves()]
        if errors: status='PARSE_ERROR'
        elif main: status='LEGAL_MOVES'  # not pedagogy validated
        else: status='THEORY'
        exporter=chess.pgn.StringExporter(headers=True,variations=True,comments=True)
        return {'fen':normalized_fen,'fen_valid':True,'status':status,
                'pgn':parsed.accept(exporter) if not errors else None,
                'tree':tree,'mainline':main,'errors':errors}
    except Exception as exc:
        return {'fen':normalized_fen,'fen_valid':True,'status':'PARSE_ERROR','pgn':None,'tree':None,'mainline':[],'errors':[str(exc)]}


def connect(db):
    c=sqlite3.connect(str(db),timeout=60)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=60000')
    return c

SCHEMA = '''
CREATE TABLE IF NOT EXISTS cdb_sources (
 id INTEGER PRIMARY KEY, filename TEXT NOT NULL, origin_path TEXT NOT NULL,
 sha256 TEXT NOT NULL UNIQUE, level TEXT, title TEXT, metadata_json TEXT NOT NULL,
 games_count INTEGER NOT NULL DEFAULT 0, chapters_count INTEGER NOT NULL DEFAULT 0,
 imported_at TEXT NOT NULL, report_json TEXT
);
CREATE TABLE IF NOT EXISTS cdb_source_paths (
 source_id INTEGER NOT NULL REFERENCES cdb_sources(id) ON DELETE CASCADE,
 origin_path TEXT NOT NULL UNIQUE, duplicate INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cdb_chapters (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES cdb_sources(id) ON DELETE CASCADE,
 original_id INTEGER NOT NULL, parent_original_id INTEGER, start_game_id INTEGER,
 title TEXT, raw_json TEXT NOT NULL, UNIQUE(source_id,original_id)
);
CREATE TABLE IF NOT EXISTS cdb_records (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES cdb_sources(id) ON DELETE CASCADE,
 original_id INTEGER NOT NULL, origin_index INTEGER NOT NULL,
 event TEXT, original_fen TEXT, normalized_fen TEXT, movetext TEXT, raw_json TEXT NOT NULL,
 record_type TEXT NOT NULL, topic TEXT NOT NULL, mate_in INTEGER, elo INTEGER,
 difficulty INTEGER, status TEXT NOT NULL, fen_valid INTEGER,
 mainline_json TEXT NOT NULL, tree_json TEXT, normalized_pgn TEXT,
 errors_json TEXT NOT NULL, normalized_movetext TEXT, normalization_json TEXT, UNIQUE(source_id,origin_index)
);
CREATE INDEX IF NOT EXISTS cdb_idx_record_topic ON cdb_records(topic, status, difficulty);
CREATE INDEX IF NOT EXISTS cdb_idx_record_source ON cdb_records(source_id, original_id);
CREATE TABLE IF NOT EXISTS cdb_exercises (
 id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL UNIQUE REFERENCES cdb_records(id) ON DELETE CASCADE,
 topic TEXT NOT NULL, difficulty INTEGER, goal_type TEXT NOT NULL, mate_in INTEGER,
 starting_fen TEXT, solution_tree_json TEXT NOT NULL, readiness TEXT NOT NULL,
 review_reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cdb_import_runs (
 id INTEGER PRIMARY KEY, started TEXT NOT NULL, finished TEXT, input_path TEXT,
 report_json TEXT
);
'''

def init_catalog(db):
    Path(db).parent.mkdir(parents=True,exist_ok=True)
    with connect(db) as c:
        c.executescript(SCHEMA)
        existing = {row['name'] for row in c.execute('PRAGMA table_info(cdb_records)')}
        if 'normalized_movetext' not in existing:
            c.execute('ALTER TABLE cdb_records ADD COLUMN normalized_movetext TEXT')
        if 'normalization_json' not in existing:
            c.execute('ALTER TABLE cdb_records ADD COLUMN normalization_json TEXT')


def _safe_archive_members(tf):
    for member in tf.getmembers():
        if not member.isfile() or not member.name.lower().endswith('.cdb'): continue
        p=pathlib.PurePosixPath(member.name)
        if p.is_absolute() or '..' in p.parts or member.issym() or member.islnk(): continue
        if member.size>150*1024*1024: raise ValueError(f'Завеликий CDB: {member.name}')
        yield member


def discover(input_path):
    """Return [(relative, bytes)], without extracting untrusted archive paths."""
    p=Path(input_path)
    if p.is_file() and tarfile.is_tarfile(p):
        out=[]
        with tarfile.open(p,'r:*') as tf:
            for member in _safe_archive_members(tf):
                f=tf.extractfile(member)
                if f: out.append((member.name,f.read()))
        return out
    if p.is_file() and p.suffix.lower()=='.cdb': return [(p.name,p.read_bytes())]
    if p.is_dir(): return [(x.relative_to(p).as_posix(),x.read_bytes()) for x in sorted(p.rglob('*')) if x.is_file() and x.suffix.lower()=='.cdb']
    raise ValueError('Очікується .cdb, tar.gz або каталог CDB')


def _count_table(src,name):
    return src.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]


def import_one(db, origin_path, blob, output_dir):
    sha=hashlib.sha256(blob).hexdigest()
    filename=Path(origin_path).name
    with connect(db) as c:
        prior=c.execute('SELECT id FROM cdb_sources WHERE sha256=?',(sha,)).fetchone()
        if prior:
            c.execute('INSERT OR IGNORE INTO cdb_source_paths(source_id,origin_path,duplicate) VALUES(?,?,1)',(prior['id'],origin_path))
            return {'file':origin_path,'sha256':sha,'duplicate':True,'source_id':prior['id'],'games':0,'chapters':0}
    if not blob.startswith(b'SQLite format 3\x00'):
        return {'file':origin_path,'sha256':sha,'error':'NOT_SQLITE','games':0,'chapters':0}
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)/'input.cdb';tmp.write_bytes(blob)
        src=sqlite3.connect('file:'+str(tmp)+'?mode=ro&immutable=1',uri=True);src.row_factory=sqlite3.Row
        try:
            check=src.execute('PRAGMA quick_check').fetchone()[0]
            if check!='ok': return {'file':origin_path,'sha256':sha,'error':'SQLITE_CHECK_FAILED: '+str(check),'games':0,'chapters':0}
            tabs={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'games' not in tabs:
                return {'file':origin_path,'sha256':sha,'error':'NO_GAMES_TABLE','games':0,'chapters':0}
            params={r['name']:r['value'] for r in src.execute('SELECT name,value FROM params')} if 'params' in tabs else {}
            chapters=[dict(r) for r in src.execute('SELECT * FROM contents ORDER BY id')] if 'contents' in tabs else []
            src_count=_count_table(src,'games')
            outdir=Path(output_dir)/sha[:12]
            outdir.mkdir(parents=True,exist_ok=True)
            stat=Counter(); errors_out=[]; n_pgn=n_fen=n_json=0; elo_count=0; candidates=0; promotions_normalized=0; records_normalized=0
            with connect(db) as c:
                cur=c.execute('INSERT INTO cdb_sources(filename,origin_path,sha256,level,title,metadata_json,imported_at) VALUES(?,?,?,?,?,?,?)',
                   (filename,origin_path,sha,'початковий' if '/beginner/' in '/'+origin_path else 'середній' if '/middle/' in '/'+origin_path else 'невідомий',params.get('title') or filename,json.dumps(params,ensure_ascii=False),now()))
                sid=cur.lastrowid
                c.execute('INSERT INTO cdb_source_paths(source_id,origin_path,duplicate) VALUES(?,?,0)',(sid,origin_path))
                for row in chapters:
                    c.execute('INSERT INTO cdb_chapters(source_id,original_id,parent_original_id,start_game_id,title,raw_json) VALUES(?,?,?,?,?,?)',
                      (sid,row['id'],row.get('parent'),row.get('gameid'),row.get('text'),json.dumps(row,ensure_ascii=False)))
                with (outdir/'records.jsonl').open('w',encoding='utf8') as fjson, (outdir/'positions.fen').open('w',encoding='utf8') as ffen, (outdir/'games.pgn').open('w',encoding='utf8') as fpgn:
                    for idx,row in enumerate(src.execute('SELECT * FROM games ORDER BY rowid')):
                        raw={k:serialize(v) for k,v in dict(row).items()}
                        text=raw.get('MoveText') or ''
                        if isinstance(text,dict): text=''
                        fen=raw.get('FEN') or None
                        if not isinstance(fen,str): fen=None
                        elo_match=ELO_RE.search(text)
                        elo=int(elo_match.group(1)) if elo_match else None
                        if elo is not None: elo_count+=1
                        clean=ELO_RE.sub('',text).strip()
                        normalized, normalization = normalize_cdb_movetext(clean)
                        promotions_normalized += normalization['promotions_normalized']
                        records_normalized += bool(normalization['promotions_normalized'])
                        parsed=chess_parse(fen,clean)
                        topic,mate_in=classify(filename,raw.get('Event'),text)
                        # all material stays a record, including text-only and parser failures
                        if parsed['status']=='THEORY': typ='theory'
                        elif parsed['status']=='EMPTY_MOVETEXT': typ='unknown'
                        elif not fen and parsed['mainline']:typ='game'
                        elif parsed['mainline']:typ='puzzle' if topic in ('мат','незахищені фігури','подвійний удар','зв’язка','відкритий напад') else 'game_fragment'
                        elif text.lstrip().startswith('{'):typ='theory'
                        else:typ='unknown'
                        degree=level(elo,len(parsed['mainline']),len(parsed['tree']['variations']) if parsed['tree'] else 0)
                        stat[parsed['status']]+=1
                        if parsed['errors']:
                            for e in parsed['errors'][:3]: errors_out.append({'record_id':raw.get('id'),'origin_index':idx,'status':parsed['status'],'error':e[:300]})
                        cur=c.execute('''INSERT INTO cdb_records(source_id,original_id,origin_index,event,original_fen,normalized_fen,movetext,raw_json,record_type,topic,mate_in,elo,difficulty,status,fen_valid,mainline_json,tree_json,normalized_pgn,errors_json,normalized_movetext,normalization_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (sid,raw.get('id') or idx,idx,raw.get('Event'),fen,parsed['fen'],text,json.dumps(raw,ensure_ascii=False),typ,topic,mate_in,elo,degree,parsed['status'],None if parsed['fen_valid'] is None else int(parsed['fen_valid']),json.dumps(parsed['mainline']),json.dumps(parsed['tree'],ensure_ascii=False) if parsed['tree'] else None,parsed['pgn'],json.dumps(parsed['errors'],ensure_ascii=False),normalized,json.dumps(normalization,ensure_ascii=False)))
                        rid=cur.lastrowid
                        if fen and (typ=='puzzle' or topic in ('ендшпіль','базові мати','незахищені фігури','подвійний удар','зв’язка','відкритий напад')):
                            # 'review_required' until explicit domain goal verification
                            goal='mate' if topic in ('мат','базові мати') else 'endgame' if topic=='ендшпіль' else 'tactic'
                            reason='Не підтверджена педагогічна мета/всі альтернативи' if parsed['status']=='LEGAL_MOVES' else 'Потрібен коректний шаховий парсинг'
                            c.execute('''INSERT INTO cdb_exercises(record_id,topic,difficulty,goal_type,mate_in,starting_fen,solution_tree_json,readiness,review_reason,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?)''',(rid,topic,degree,goal,mate_in,parsed['fen'],json.dumps(parsed['tree'] or {},ensure_ascii=False),'REVIEW_REQUIRED',reason,now()))
                            candidates+=1
                        export={'id':rid,'source_id':sid,'source_record_id':raw.get('id'),'type':typ,'topic':topic,
                            'fen_original':fen,'fen':parsed['fen'],'move_text_original':text,
                            'elo':elo,'difficulty':degree,'mate_in':mate_in,'status':parsed['status'],
                            'normalized_movetext':normalized,'normalization':normalization, 'mainline_uci':parsed['mainline'],'solution_tree':parsed['tree'], 'errors':parsed['errors'],'raw':raw}
                        fjson.write(json.dumps(export,ensure_ascii=False)+'\n'); n_json+=1
                        if parsed['fen_valid'] is True and parsed['fen']:
                            ffen.write(f'{parsed["fen"]}\t{sid}:{raw.get("id")}\n');n_fen+=1
                        if parsed['pgn']:
                            fpgn.write(parsed['pgn']+'\n\n');n_pgn+=1
                (outdir/'chapters.json').write_text(json.dumps(chapters,ensure_ascii=False,indent=2),encoding='utf8')
                (outdir/'source.json').write_text(json.dumps({'id':sid,'sha256':sha,'filename':filename,'origin_path':origin_path,'params':params},ensure_ascii=False,indent=2),encoding='utf8')
                report={'file':origin_path,'filename':filename,'sha256':sha,'source_id':sid,
                    'duplicate':False,'games':src_count,'chapters':len(chapters),'parsed_statuses':dict(stat),
                    'exported_json':n_json,'exported_fen':n_fen,'exported_pgn':n_pgn,
                    'elo_records':elo_count,'normalizer_version':NORMALIZER_VERSION,'promotion_replacements':promotions_normalized,'records_with_promotions':records_normalized,'exercise_candidates':candidates,
                    'ready_exercises':0,'needs_review':candidates,'errors':len(errors_out),
                    'parser_available':CHESS_AVAILABLE,'output_dir':str(outdir)}
                with (outdir/'validation_errors.csv').open('w',encoding='utf8',newline='') as fe:
                    w=csv.DictWriter(fe,['record_id','origin_index','status','error']);w.writeheader();w.writerows(errors_out)
                (outdir/'conversion_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
                c.execute('UPDATE cdb_sources SET games_count=?,chapters_count=?,report_json=? WHERE id=?',
                          (src_count,len(chapters),json.dumps(report,ensure_ascii=False),sid))
            return report
        finally: src.close()


def import_path(db,input_path,output_dir):
    init_catalog(db)
    t0=time.monotonic()
    with connect(db) as c:
        cur=c.execute('INSERT INTO cdb_import_runs(started,input_path) VALUES(?,?)',(now(),str(input_path)));run_id=cur.lastrowid
    entries=discover(input_path)
    out=[]
    for name,blob in entries:
        try: out.append(import_one(db,name,blob,output_dir))
        except Exception as exc: out.append({'file':name,'error':str(exc),'games':0,'chapters':0})
    with connect(db) as c:
        totals=c.execute('SELECT COUNT(*) sources, COALESCE(SUM(games_count),0) games, COALESCE(SUM(chapters_count),0) chapters FROM cdb_sources').fetchone()
        statuses={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM cdb_records GROUP BY status')}
        candidates=c.execute('SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
    report={'run_id':run_id,'input':str(input_path),'files_seen':len(entries), 'new_sources':sum(not r.get('duplicate') and not r.get('error') for r in out),
            'duplicates_seen':sum(bool(r.get('duplicate')) for r in out), 'failed_files':sum(bool(r.get('error')) for r in out),
            'database_totals':dict(totals),'record_statuses':statuses,'exercise_candidates':candidates,
            'ready_exercises':0,'normalizer_version':NORMALIZER_VERSION,'promotion_replacements':sum(r.get('promotion_replacements',0) for r in out),'records_with_promotions':sum(r.get('records_with_promotions',0) for r in out),'python_chess_available':CHESS_AVAILABLE,'seconds':round(time.monotonic()-t0,2),'files':out}
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    (Path(output_dir)/'import_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    with connect(db) as c:c.execute('UPDATE cdb_import_runs SET finished=?,report_json=? WHERE id=?',(now(),json.dumps(report,ensure_ascii=False),run_id))
    return report


def catalog_query(db, topic=None, status=None, source_id=None, record_type=None,
                  difficulty=None, limit=50, offset=0, include_book_text=False):
    # Use topic assigned to the exercise, not stale r.topic from the CDB import.
    limit=max(1,min(int(limit),250));offset=max(0,int(offset))
    sql="""SELECT r.id,r.source_id,s.filename,r.original_id,r.event,
         r.normalized_fen AS fen,r.record_type,
         COALESCE(e.topic,r.topic) AS topic,COALESCE(e.mate_in,r.mate_in) AS mate_in,r.elo,
         COALESCE(e.difficulty,r.difficulty) AS difficulty,r.status
         FROM cdb_records r JOIN cdb_sources s ON s.id=r.source_id
         LEFT JOIN cdb_exercises e ON e.record_id=r.id WHERE 1=1"""
    args=[]
    if not include_book_text and topic is not None:
        sql += " AND NOT (r.normalized_fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' AND COALESCE(r.mainline_json,'[]')='[]')"
    for cond,value in [('e.topic=?',topic),('r.status=?',status),
                       ('r.source_id=?',source_id),('r.record_type=?',record_type),
                       ('COALESCE(e.difficulty,r.difficulty)=?',difficulty)]:
        if value is not None:
            sql+=' AND '+cond
            args.append(value)
    with connect(db) as c:
        n=c.execute('SELECT COUNT(*) FROM ('+sql+')',args).fetchone()[0]
        rows=[dict(x) for x in c.execute(sql+' ORDER BY r.id LIMIT ? OFFSET ?',args+[limit,offset])]
    return {'total':n,'limit':limit,'offset':offset,'items':rows}


def exercise_catalog_sources(db, topic=None):
    """Available CDB files for the selected exercise topic (not stale import topics)."""
    join = (" FROM cdb_exercises e "
            "JOIN cdb_records r ON r.id=e.record_id "
            "JOIN cdb_sources s ON s.id=r.source_id")
    where = " WHERE e.topic=?" if topic else ""
    args = [topic] if topic else []
    with connect(db) as c:
        rows = c.execute(
            "SELECT s.id AS source_id,s.filename,COUNT(*) AS exercises" +
            join + where + " GROUP BY s.id,s.filename ORDER BY s.filename COLLATE NOCASE",
            args).fetchall()
    return {'topic':topic,'sources':[dict(row) for row in rows]}


def exercise_catalog_numbers(db, topic, source_id):
    """CDB original game IDs for one topic and source, sorted numerically."""
    with connect(db) as c:
        rows = c.execute("""SELECT DISTINCT r.original_id
            FROM cdb_exercises e
            JOIN cdb_records r ON r.id=e.record_id
            WHERE e.topic=? AND r.source_id=? AND r.original_id IS NOT NULL
            ORDER BY r.original_id""", (topic,source_id)).fetchall()
    return {'topic':topic,'source_id':source_id,
            'numbers':[row['original_id'] for row in rows]}


def exercise_catalog_query(db, topic=None, limit=20, offset=0,
                           source_id=None, original_id=None):
    """Page the actual training catalogue by topic, CDB file and source game ID.

    A CDB task number is r.original_id within r.source_id, not a global exercise ID.
    All filters are applied to the COUNT and to the SELECT identically.
    """
    limit=max(1,min(int(limit),100)); offset=max(0,int(offset))
    where=[];args=[]
    if topic:
        where.append('e.topic=?');args.append(topic)
    if source_id is not None:
        where.append('r.source_id=?');args.append(int(source_id))
    if original_id is not None:
        where.append('r.original_id=?');args.append(int(original_id))
    condition=(' WHERE '+' AND '.join(where)) if where else ''
    join=(' FROM cdb_exercises e JOIN cdb_records r ON r.id=e.record_id '
          'JOIN cdb_sources s ON s.id=r.source_id')
    with connect(db) as c:
        total=c.execute('SELECT COUNT(*)'+join+condition,args).fetchone()[0]
        rows=c.execute("""SELECT r.id,r.source_id,s.filename,r.original_id,r.event,
            r.normalized_fen AS fen,r.record_type,e.topic,e.mate_in,r.elo,
            e.difficulty,r.status,e.id AS exercise_id
            """+join+condition+' ORDER BY s.filename COLLATE NOCASE, r.original_id, e.id LIMIT ? OFFSET ?',
            args+[limit,offset]).fetchall()
    return {'total':total,'limit':limit,'offset':offset,
            'items':[dict(row) for row in rows]}


def clear_catalog(db):
    """Remove only imported chess catalog; retain users and training games."""
    init_catalog(db)
    with connect(db) as c:
        c.execute('DELETE FROM cdb_sources')  # cascading records / chapters / exercises / paths
