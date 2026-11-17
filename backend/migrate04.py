"""Apply safe MVP 0.4 session migration and inspect full exercise availability."""
import argparse
import json
from pathlib import Path
from exercise04 import init_exercises04, available_counts


def main():
    parser=argparse.ArgumentParser(description='Міграція AgentChess MVP 0.4')
    parser.add_argument('--db',type=Path,default=Path('data/agentchess.sqlite3'))
    args=parser.parse_args()
    if not args.db.is_file():
        raise SystemExit('Немає SQLite-бази: '+str(args.db))
    init_exercises04(args.db)
    result=available_counts(args.db)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['total']!=7851:
        print('Увага: поточна кількість вправ відрізняється від еталонних 7851; перевірте каталог.')

if __name__=='__main__': main()
