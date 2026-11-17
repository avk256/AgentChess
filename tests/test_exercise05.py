"""MVP 0.5 regression tests. Requires python-chess (installed on target Xubuntu)."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

chess=pytest.importorskip('chess')
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'backend'))
from exercise05 import flatten_source_tree, legal_first_variation, expand_sources, SOURCE_TOPICS


def test_multiple_root_variations_and_nested_comments():
    tree={'variations':[
        {'uci':'e2e4','san':'e4','comment':'Головне продовження','starting_comment':'План:',
         'nags':[1],'children':[
            {'uci':'e7e5','san':'e5','comment':'захист 1','children':[]},
            {'uci':'c7c5','san':'c5','comment':'захист 2','children':[]}]},
        {'uci':'d2d4','san':'d4','comment':'другий початок','children':[]}]}
    result=flatten_source_tree(chess.STARTING_FEN,json.dumps(tree))
    assert result['total_nodes']==5
    assert result['root_variations']==2
    assert result['blocked_nodes']==0
    assert result['nodes'][1]['starting_comment']=='План:'
    assert result['nodes'][1]['nags']==[1]
    assert len(result['nodes'][1]['children'])==2
    assert result['nodes'][3]['comment']=='захист 2'
    assert result['nodes'][4]['fen'] != result['nodes'][1]['fen']


def test_null_move_keeps_all_branches_without_inventing_fen():
    tree={'variations':[
        {'uci':'0000','san':'--','children':[{'uci':'a2a4','san':'a4','children':[]}]},
        {'uci':'e2e4','san':'e4','children':[]}]}
    out=flatten_source_tree(chess.STARTING_FEN,json.dumps(tree))
    assert len(out['nodes'])==4
    assert out['nodes'][1]['fen'] is None
    assert out['nodes'][2]['fen'] is None
    assert out['nodes'][3]['playable'] is True
    assert out['nodes'][0]['children']==[1,3]
    assert out['blocked_nodes']==2
    assert legal_first_variation(chess.STARTING_FEN,json.dumps(tree))==['e2e4']


def test_invalid_move_is_visible_but_not_accepted():
    tree={'variations':[{'uci':'a1a8','san':'Ra8','children':[]},
                        {'uci':'e2e4','san':'e4','children':[]}]}
    out=flatten_source_tree(chess.STARTING_FEN,json.dumps(tree))
    assert out['nodes'][1]['playable'] is False
    assert out['nodes'][2]['playable'] is True


def test_all_fifteen_sources_mapped():
    assert len(SOURCE_TOPICS)==15
    assert SOURCE_TOPICS['School2.ru.cdb']=='тактичні комбінації'
    assert SOURCE_TOPICS['win_trap.ru.cdb']=='дебютні пастки'
    assert SOURCE_TOPICS['lysenko.cdb']=='оцінка позиції'


def test_expansion_idempotent_on_real_db_copy(tmp_path):
    project=Path(__file__).resolve().parents[1]
    candidates=[project/'data/agentchess.sqlite3',project/'data/agentchess_021_test.sqlite3']
    source=next((x for x in candidates if x.exists()),None)
    if source is None:
        pytest.skip('Real CDB sqlite database is on the user Xubuntu system')
    target=tmp_path/'test.sqlite3'
    src=sqlite3.connect(str(source));dst=sqlite3.connect(str(target))
    src.backup(dst);src.close();dst.close()
    before=sqlite3.connect(str(target)).execute('SELECT count(*) FROM cdb_exercises').fetchone()[0]
    first=expand_sources(target)
    after=sqlite3.connect(str(target)).execute('SELECT count(*) FROM cdb_exercises').fetchone()[0]
    second=expand_sources(target)
    # The source DB can be either the original 7,851-exercise catalog
    # or an already expanded 14,343-exercise catalog. 0 additions on
    # the first run is correct for the latter (idempotency).
    assert first['new_exercises'] >= 0
    assert after == before + first['new_exercises']
    assert second['new_exercises'] == 0
    final=sqlite3.connect(str(target)).execute(
        'SELECT COUNT(*) FROM cdb_exercises').fetchone()[0]
    assert final == after
    if before == 14343:
        assert first['new_exercises'] == 0
    elif before == 7851:
        assert first['new_exercises'] == 6492
        assert after == 14343
    check=sqlite3.connect(str(target))
    assert check.execute('SELECT count(*) FROM cdb_records').fetchone()[0]==18805
    assert check.execute('SELECT count(*) FROM cdb_sources').fetchone()[0]==33
    check.close()
