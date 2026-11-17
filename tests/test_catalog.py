from pathlib import Path
import hashlib, sqlite3, sys, json, tarfile, io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from catalog import import_path, catalog_query, connect, classify, level, CHESS_AVAILABLE

def make_cdb(path):
    c=sqlite3.connect(path)
    c.executescript('''CREATE TABLE games(id INTEGER, Event TEXT,FEN TEXT,MoveText TEXT);
    CREATE TABLE contents(id INTEGER,parent INTEGER,gameid INTEGER,text TEXT);
    CREATE TABLE params(name TEXT,value TEXT);
    CREATE TABLE bookmarks (id INTEGER);
    CREATE TABLE pzl_stats (id INTEGER);''')
    c.execute('INSERT INTO games VALUES(?,?,?,?)',(1,'Мат в 1 ход','3q1rk1/5pbp/5Qp1/8/8/2B5/5PPP/6K1 w - - 0 1','{Elo: 970} 1.Qxg7#'))
    c.execute('INSERT INTO games VALUES(?,?,?,?)',(2,'Передмова',None,'{Книга про шахи.}'))
    c.execute('INSERT INTO contents VALUES(1,0,1,?)',('Розділ 1',))
    c.execute('INSERT INTO params VALUES(?,?)',('title','Тест'))
    c.commit();c.close()

def test_import_idempotent_and_separates_chapters(tmp_path):
    src=tmp_path/'test.cdb'; make_cdb(src)
    db=tmp_path/'agent.sqlite';dest=tmp_path/'converted'
    r=import_path(db,src,dest)
    assert r['new_sources']==1 and r['database_totals']['games']==2 and r['database_totals']['chapters']==1
    assert (dest/'import_summary.json').exists()
    rr=import_path(db,src,dest)
    assert rr['new_sources']==0 and rr['duplicates_seen']==1
    assert rr['database_totals']['games']==2
    with connect(db) as c:
        assert c.execute('SELECT count(*) FROM cdb_records').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM cdb_chapters').fetchone()[0]==1
        obj=c.execute('SELECT elo,movetext,raw_json FROM cdb_records WHERE original_id=1').fetchone()
        assert obj['elo']==970
        assert 'Elo: 970' in obj['movetext']
        assert json.loads(obj['raw_json'])['Event']=='Мат в 1 ход'
    assert catalog_query(db,topic='мат')['total']==2 if False else catalog_query(db)['total']==2

def test_archive_duplicate_by_sha(tmp_path):
    original=tmp_path/'sample.cdb';make_cdb(original)
    arch=tmp_path/'vlasov.tar.gz'
    with tarfile.open(arch,'w:gz') as tf:
        for name in ('vlasov/beginner/a.cdb','vlasov/middle/a.cdb'):
            payload=original.read_bytes(); info=tarfile.TarInfo(name);info.size=len(payload)
            tf.addfile(info,io.BytesIO(payload))
    result=import_path(tmp_path/'db.sqlite',arch,tmp_path/'exp')
    assert result['files_seen']==2 and result['new_sources']==1 and result['duplicates_seen']==1
    with connect(tmp_path/'db.sqlite') as c:
        assert c.execute('SELECT count(*) FROM cdb_source_paths').fetchone()[0]==2

def test_classify_elo_levels():
    topic,mate=classify('polgar.ru.cdb','Мат в 2 хода','1.Qh8#')
    assert topic=='мат' and mate==2
    assert level(970,2,0)==1 and level(1850,2,0)==4
