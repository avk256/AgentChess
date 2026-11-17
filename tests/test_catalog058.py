"""The catalog must submit a stable topic key rather than the display label with count."""
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

class OptionParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.options=[]; self.option=None
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='select' and attrs.get('id')=='catTopic': self.active=True
        elif tag=='option' and self.active: self.option={'value':attrs.get('value'),'text':''}
    def handle_data(self,data):
        if self.option is not None:self.option['text']+=data
    def handle_endtag(self,tag):
        if tag=='option' and self.option is not None:
            self.options.append(self.option);self.option=None
        elif tag=='select' and self.active:self.active=False

def test_all_catalog_options_have_stable_values():
    p=OptionParser();p.feed((ROOT/'frontend/index.html').read_text(encoding='utf8'))
    assert len(p.options)>=13
    for o in p.options:
        assert o['value'] is not None, f"Option lacks explicit value: {o['text']}"
        if o['value'] != '': assert o['value']==o['text'].strip(), o
    assert any(o['value']=='подвійний удар' for o in p.options)
    assert any(o['value']=='тактичні комбінації' for o in p.options)

def test_count_display_cannot_change_selected_topic_value():
    text=(ROOT/'frontend/index.html').read_text(encoding='utf8')
    assert 'option.value=canonical;' in text
    assert 'option.dataset.topicValue=canonical' in text
    assert "option.textContent=title+(num?' ('+num+')':'');" in text

def test_real_database_catalog_count_if_available():
    import pytest
    if not (ROOT/'backend/catalog.py').exists(): pytest.skip('Standalone update package has no backend')
    from catalog import exercise_catalog_query
    db=ROOT/'data/agentchess.sqlite3'
    if not db.exists(): return
    # The patch is intentionally small; verify counts only when actual database is available.
    assert exercise_catalog_query(db,'подвійний удар',20,0)['total']==284
    assert exercise_catalog_query(db,'тактичні комбінації',20,0)['total']==3393
