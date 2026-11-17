"""Offline checks not requiring python-chess."""
import ast
from pathlib import Path


def test_new_code_compiles():
    base=Path(__file__).resolve().parents[1]
    for name in ('exercise05.py','exercise05_topics.py','exercise04.py','app.py'):
        ast.parse((base/'backend'/name).read_text(encoding='utf-8'))


def test_appearance_and_variation_controls_present():
    html=(Path(__file__).resolve().parents[1]/'frontend/index.html').read_text()
    for required in ('id="uiTheme"', 'id="solChoice"', 'id="solutionBranches"',
                     'function loadUiTheme()', '/exercises/', '/tree'):
        assert required in html
