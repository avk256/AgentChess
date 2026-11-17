"""Audit source usage and misleading mainline null moves, without modifying data.

python backend/audit042.py --db data/agentchess.sqlite3 --out data/audit_042.json
"""
import argparse
import json
import sqlite3
from pathlib import Path


def audit(db):
    con=sqlite3.connect(f'file:{Path(db).resolve()}?mode=ro',uri=True)
    con.row_factory=sqlite3.Row
    source_rows=[dict(r) for r in con.execute('''SELECT s.filename,s.level,s.games_count,
              COUNT(e.id) exercises FROM cdb_sources s
              LEFT JOIN cdb_records r ON r.source_id=s.id
              LEFT JOIN cdb_exercises e ON e.record_id=r.id
              GROUP BY s.id ORDER BY exercises DESC,s.filename''')]
    topics={}
    examples=[]
    for r in con.execute('''SELECT e.id,e.topic,r.original_id,r.mainline_json,
                        r.tree_json,s.filename FROM cdb_exercises e
                        JOIN cdb_records r ON r.id=e.record_id
                        JOIN cdb_sources s ON s.id=r.source_id'''):
        t=topics.setdefault(r['topic'],{'total':0,'zero_ply':0,'one_ply':0,
                                        'multi_ply':0,'contains_null_marker':0,
                                        'root_alternatives':0})
        t['total']+=1
        try:line=json.loads(r['mainline_json'] or '[]')
        except (TypeError,ValueError):line=[]
        if not isinstance(line,list):line=[]
        t['zero_ply' if not line else 'one_ply' if len(line)==1 else 'multi_ply']+=1
        if '0000' in line:
            t['contains_null_marker']+=1
            if len(examples)<20:examples.append({'exercise_id':r['id'],'source':r['filename'],
                'source_record_id':r['original_id'],'first_null_ply':line.index('0000')+1})
        try:
            tree=json.loads(r['tree_json'] or '{}')
            if len(tree.get('variations') or [])>1:t['root_alternatives']+=1
        except (ValueError,TypeError,AttributeError):pass
    con.close()
    return {'total_exercises':sum(x['exercises'] for x in source_rows),
            'imported_sources':len(source_rows),
            'used_sources':sum(x['exercises']>0 for x in source_rows),
            'unused_sources':sum(x['exercises']==0 for x in source_rows),
            'sources':source_rows,'topics':topics,
            'total_null_marker_exercises':sum(x['contains_null_marker'] for x in topics.values()),
            'null_marker_examples':examples,
            'notes':['0000 is a PGN/CDB null-move marker, not a legal user chess move.',
                     'Source usage counts include only exercise candidates, not theoretical catalog records.',
                     'Alternative PGN branches require a dedicated viewer; the step-by-step solution presents the mainline only.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',default='data/agentchess.sqlite3');p.add_argument('--out',default='data/audit_042.json')
    a=p.parse_args();result=audit(a.db)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('total_exercises','imported_sources','used_sources','unused_sources','total_null_marker_exercises')},ensure_ascii=False,indent=2))
