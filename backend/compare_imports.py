"""Compare 0.2 baseline import_summary.json and 0.2.1 trial import_summary.json.

Example:
  python backend/compare_imports.py --before backups/import_summary_020.json \\
      --after data/converted_021/import_summary.json --out reports/compare_020_021.json
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

EXPECTED = {'sources': 33, 'games': 18805, 'chapters': 437}

def compare(before, after):
    a, b = before['record_statuses'], after['record_statuses']
    keys = sorted(set(a) | set(b))
    statuses = {key: {'before': a.get(key, 0), 'after': b.get(key, 0), 'delta': b.get(key, 0) - a.get(key, 0)} for key in keys}
    out = {'before': {k:before.get(k) for k in ('database_totals','record_statuses','exercise_candidates')},
           'after': {k:after.get(k) for k in ('database_totals','record_statuses','exercise_candidates','promotion_replacements','records_with_promotions','normalizer_version')},
           'statuses': statuses,
           'checks': {
             'dataset_integrity': all(after['database_totals'].get(k) == v for k,v in EXPECTED.items()),
             'all_records_accounted_for': sum(b.values()) == EXPECTED['games'],
             'parser_available': after.get('python_chess_available') is True,
             'no_cdb_open_failures': after.get('failed_files') == 0,
             'parse_errors_not_increased': b.get('PARSE_ERROR',0) <= a.get('PARSE_ERROR',0),
             'original_1320_errors_removed': b.get('PARSE_ERROR',0) == 0,
           }}
    return out

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--out', default='reports/compare_020_021.json')
    args = parser.parse_args()
    result = compare(json.loads(Path(args.before).read_text(encoding='utf-8')),
                     json.loads(Path(args.after).read_text(encoding='utf-8')))
    dest = Path(args.out); dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'statuses':result['statuses'], 'checks':result['checks']},ensure_ascii=False,indent=2))
    print('Report:',dest)
    if not all(result['checks'][x] for x in ('dataset_integrity','all_records_accounted_for','parser_available','no_cdb_open_failures')):
        raise SystemExit(2)
