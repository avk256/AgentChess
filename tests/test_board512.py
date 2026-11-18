"""Regression tests for the unified history controls in MVP 0.5.12."""
from html.parser import HTMLParser
from pathlib import Path
import re

HTML = Path(__file__).resolve().parents[1] / 'frontend' / 'index.html'

class Structure(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.ids={}; self.handlers={}
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); element=(tag,a); self.stack.append(element)
        if 'id' in a:
            self.ids.setdefault(a['id'], []).append(tuple(x[1].get('id') or x[1].get('class','') for x in self.stack))
            self.handlers[a['id']]=a.get('onclick','')
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs);self.stack.pop()
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break

def source(): return HTML.read_text(encoding='utf-8')
def structure():
    p=Structure();p.feed(source().split('<script>')[0]);return p

def test_single_history_panel_directly_below_board():
    p=structure()
    assert len(p.ids['playbackPanel'])==1
    path=p.ids['playbackPanel'][0]
    assert 'board-box' in path and 'side' not in path
    assert 'board-frame' not in path

def test_no_duplicate_navigation_buttons():
    p=structure()
    for id_ in ('historyPrev','historyNext','historyCounter','historyReturn'):
        assert len(p.ids[id_])==1
    for id_ in ('boardPrev','boardNext','boardCounter'):
        assert id_ not in p.ids

def test_one_shared_dispatcher():
    p=structure(); s=source()
    assert p.handlers['historyPrev']=='historyStep(-1)'
    assert p.handlers['historyNext']=='historyStep(1)'
    assert 'function historyStep(delta)' in s
    assert 'if(playback){playbackStep(delta);return}' in s
    assert 'await showGameHistory()' in s
    assert 'analysisTimeline||exerciseTimeline' in s

def test_panel_not_hidden_on_clear_or_start():
    s=source()
    assert 'class="playback-panel" id="playbackPanel"' in s
    assert "$('playbackPanel').classList.add('hidden')" not in s
    assert "$('playbackPanel').classList.remove('hidden')" not in s

def test_review_restores_live_position():
    s=source()
    assert 'if(!silent&&before){fen=before.fen;playerBlack=before.playerBlack;render()}' in s
    assert 'function closePlayback()' in s
    assert 'if(playbackBefore)playbackBefore.fen=r.timeline[r.timeline.length-1].fen' in s

def test_history_uses_engine_position_and_moves():
    s=source()
    assert "api('/games/'+gid+'/timeline')" in s
    assert "openPlayback(r.timeline,'Історія партії зі Stockfish'" in s
    assert 'function playbackStep(direction)' in s
