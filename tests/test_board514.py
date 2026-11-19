"""MVP 0.5.14 editor regressions, run with pytest (no Node test runner)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
BACKEND = (ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')


def function(name):
    match = re.search(r'(?:async )?function ' + re.escape(name) + r'\([^)]*\)\s*\{', HTML)
    assert match, f'Missing JS function: {name}'
    start = match.end()
    # Slice up to the following function declaration; sufficient for source-level invariants.
    end = re.search(r'\n(?:async )?function [A-Za-z_$]', HTML[start:])
    return HTML[start:start+end.start()] if end else HTML[start:]


def test_editor_available_in_stockfish_mode():
    assert 'id="positionEditor"' in HTML
    assert 'id="editorPalette"' in HTML
    assert 'onclick="togglePositionEditor()"' in HTML
    assert 'id="gameOpts"' in HTML


def test_board_clicks_and_keyboard_are_routed_to_editor():
    render = function('render')
    assert 'editorActive?editorDraft.pieces:decode(fen)' in render
    assert 'if(editorActive)editorClick(sq);else click(sq,piece,d)' in render
    assert "if(editorActive)editorClick(sq);else click(sq,piece,d)" in render


def test_editing_does_not_alter_server_game_or_live_fen():
    change = function('editorChanged')
    assert 'editorDraft.castle' in change
    assert 'editorDraft.ep' in change
    assert 'gid=' not in change
    assert 'fen=' not in change
    assert 'editorOriginal={fen,playerBlack,gid,gameActive}' in function('openPositionEditor')
    assert 'fen=editorOriginal.fen' in function('cancelPositionEditor')


def test_editor_preserves_all_six_fen_fields():
    for field in ('pieces','turn','castle','ep','half','full'):
        assert 'parts[' in function('parseEditorFen')
        assert 'd.' + field in function('makeEditorFen')
    assert "rows.join('/')+' '+d.turn" in function('makeEditorFen')


def test_editor_supports_placement_erase_and_move():
    code = function('editorClick')
    assert "editorTool==='erase'" in code
    assert "editorTool==='move'" in code
    assert 'editorDraft.pieces[i]=editorTool' in code
    assert 'editorDraft.pieces[orig]' in code
    assert 'editorPointer' in function('draggingEnd')


def test_editor_validates_before_creating_game_and_preserves_draft_on_failure():
    body = function('applyEditorPosition')
    assert body.index("api('/position/validate'") < body.index("api('/games'")
    assert 'if(editorActive)editorSetStatus' in body
    assert 'editorActive=false' in body
    assert 'check.fen' in body


def test_new_game_button_uses_editor_draft_without_resetting_it_first():
    start = function('start')
    assert start.index('if(editorActive){await applyEditorPosition();return}') < start.index('analysisTimeline=null')


def test_backend_rejects_invalid_and_terminal_positions():
    assert "@app.post('/api/position/validate')" in BACKEND
    assert 'board=board_of(a.fen)' in BACKEND
    assert "board.is_game_over(claim_draw=True)" in BACKEND
    assert "@app.post('/api/games')" in BACKEND
    assert 'return _start_game' in BACKEND


def test_existing_playback_and_solved_task_navigation_untouched():
    for name in ('historyStep','playbackStep','refreshBoardNavigation','solveWithStockfish'):
        function(name)
    assert 'id="historyPrev"' in HTML
    assert 'id="historyNext"' in HTML


def test_game_mode_has_flip_orientation_and_standard_palette():
    assert "playerBlack=$('color').value==='black'" in function('openPositionEditor')
    assert "'KQRBNPkqrbnp'" in function('editorPaletteRender')
    assert "['K','Q','k','q']" in function('editorSyncOptions')
