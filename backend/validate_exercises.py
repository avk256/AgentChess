#!/usr/bin/env python3
"""Validate imported exercise candidates against chess rules and optionally Stockfish."""
import argparse, json, os
from pathlib import Path
from exercise03 import validate_catalog, TOPICS, init_exercises

def main():
    root=Path(__file__).resolve().parent.parent
    p=argparse.ArgumentParser(description='AgentChess MVP 0.3: safe exercise validation')
    p.add_argument('--db',default=str(root/'data'/'agentchess.sqlite3'))
    p.add_argument('--stockfish',default=os.environ.get('STOCKFISH_PATH','/usr/games/stockfish'))
    p.add_argument('--topic',action='append',choices=TOPICS,help='Repeat to validate several topics; default: all')
    p.add_argument('--limit-per-topic',type=int,default=150,help='0 = all; default 150 per topic')
    p.add_argument('--think-time',type=float,default=.12)
    p.add_argument('--min-gap',type=int,default=90,help='centipawns difference over second best move')
    p.add_argument('--reset',action='store_true',help='reset selected topics before validation')
    p.add_argument('--out',default=str(root/'data'/'exercise_validation_03.json'))
    a=p.parse_args()
    if a.limit_per_topic < 0 or a.think_time <= 0 or a.min_gap < 0:p.error('Некоректні параметри')
    result=validate_catalog(a.db,a.stockfish,a.topic,a.limit_per_topic,a.think_time,a.min_gap,a.reset)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print('Звіт:',dest)

if __name__=='__main__':main()
