"""CLI full batch CDB import; safe to run repeatedly (SHA-256 idempotency)."""
import argparse, json, os
from pathlib import Path
from catalog import import_path, clear_catalog
ROOT=Path(__file__).resolve().parent.parent
if __name__=='__main__':
    ap=argparse.ArgumentParser(description='AgentChess CDB importer v0.2.1')
    ap.add_argument('input',help='vlasov.tar.gz, .cdb or directory')
    ap.add_argument('--db',default=str(ROOT/'data'/'agentchess.sqlite3'))
    ap.add_argument('--output',default=str(ROOT/'data'/'converted'))
    ap.add_argument('--rebuild',action='store_true',help='Перестворити каталог і повторно перевірити MoveText')
    a=ap.parse_args()
    if a.rebuild: clear_catalog(a.db)
    r=import_path(a.db,a.input,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2,ensure_ascii=False))
    print('Файл звіту:',str(Path(a.output)/'import_summary.json'))
