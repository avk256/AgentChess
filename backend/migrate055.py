"""MVP 0.5.5: idempotent categorization-only migration.

Usage: python backend/migrate055.py --db data/agentchess.sqlite3 [--dry-run]
No reimport, no deletion of original CDB records or user history.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from exercise055 import migrate_endgame_topics, topic_sources, START_FEN


def migration_report(db, dry_run=False):
    db=Path(db)
    if not db.is_file():
        raise FileNotFoundError(f'Базу не знайдено: {db}')
    with sqlite3.connect(db) as c:
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':
            raise RuntimeError('SQLite integrity_check failed: '+str(integrity))
        originals=c.execute('SELECT COUNT(*) FROM cdb_records').fetchone()[0]
        before=c.execute('SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
        sources=c.execute('SELECT COUNT(*) FROM cdb_sources').fetchone()[0]
        book_text=c.execute('''SELECT COUNT(*) FROM cdb_records
          WHERE normalized_fen=? AND COALESCE(mainline_json,'[]')='[]' ''',(START_FEN,)).fetchone()[0]
    change=migrate_endgame_topics(db,dry_run=dry_run)
    data=topic_sources(db)
    if dry_run and change['reclassified']:
        # Reflect the predicted post-migration topic distribution in the preview.
        topics={t['topic']:t for t in data['topics']}
        basic=topics.pop('базові мати',None)
        if basic:
            end=topics.setdefault('ендшпіль',{'topic':'ендшпіль','count':0,'sources':[]})
            end['count']+=basic['count']
            end['sources'].extend(basic['sources'])
        data['topics']=sorted(topics.values(),key=lambda x:x['topic'])
    with sqlite3.connect(db) as c:
        after=c.execute('SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
    if before!=after:
        raise RuntimeError('Змінилася кількість вправ — міграцію зупинено')
    return {'version':'0.5.5','dry_run':dry_run,'integrity_check':integrity,
            'source_records':originals,'source_files':sources,'exercises':after,
            'hidden_standard_start_book_text':book_text,
            'reclassification':change,'topic_summary':data['topics'],
            'selectable_exercises':data['total']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--out')
    a=parser.parse_args()
    result=migration_report(a.db,dry_run=a.dry_run)
    payload=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:
        out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(payload+'\n',encoding='utf-8')
    print(payload)

if __name__=='__main__':main()
