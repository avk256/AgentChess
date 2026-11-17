"""Non-destructive MVP 0.5.3 migration for mate filters and game history."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
from exercise053 import migrate_mate_lengths
from stockfish053 import init_stockfish053


def main():
    p=argparse.ArgumentParser(description='AgentChess MVP 0.5.3 migration')
    p.add_argument('--db',required=True)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--out')
    args=p.parse_args()
    db=Path(args.db)
    if not db.is_file():p.error(f'Базу не знайдено: {db}')
    with sqlite3.connect(db) as c:
        pre=c.execute('PRAGMA integrity_check').fetchone()[0]
        before={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                for t in ('cdb_records','cdb_sources','cdb_exercises','users','games')}
    if pre!='ok':raise RuntimeError('SQLite integrity_check: '+pre)
    result=migrate_mate_lengths(db,dry_run=args.dry_run)
    if not args.dry_run:
        init_stockfish053(db)
    with sqlite3.connect(db) as c:
        after={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
               for t in before}
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity!='ok' or before!=after:
        raise RuntimeError('Порушено цілісність або змінилися кількості вихідних записів')
    report={'version':'0.5.3','dry_run':args.dry_run,'integrity':integrity,
            'table_counts_before':before,'table_counts_after':after,
            'mate_author_length':result}
    text=json.dumps(report,ensure_ascii=False,indent=2)
    print(text)
    if args.out:
        target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')

if __name__=='__main__':main()
