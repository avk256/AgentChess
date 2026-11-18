"""Regression checks for playback navigation after the asynchronous animation ends.

Tests use pytest and Python stdlib only. No browser or Node test runner required.
"""
from pathlib import Path
import re

HTML = Path(__file__).resolve().parents[1] / "frontend" / "index.html"


def source():
    return HTML.read_text(encoding="utf-8")


def body_of_function(name):
    """Extract JS function body, accounting for nested curly braces and strings."""
    text = source()
    match = re.search(rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    assert match, f"Function {name} is missing"
    pos = match.end()
    depth = 1
    quote = None
    backslash = False
    for idx in range(pos, len(text)):
        ch = text[idx]
        if quote:
            if backslash:
                backslash = False
            elif ch == "\\":
                backslash = True
            elif ch == quote:
                quote = None
        elif ch in ("'", '"', '`'):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[pos:idx]
    raise AssertionError(f"Unterminated function {name}")


def test_animation_restores_history_buttons_after_move_busy_clears():
    body = body_of_function("animateUciSequence")
    finally_block = body.split("finally", 1)[1]
    assert "if(sequence===moveGeneration)" in finally_block
    assert "moveBusy=false" in finally_block
    assert "refreshBoardNavigation()" in finally_block
    assert finally_block.index("moveBusy=false") < finally_block.index("refreshBoardNavigation()")


def test_buttons_follow_playback_cursor_not_just_first_back_step():
    body = body_of_function("refreshBoardNavigation")
    assert "playbackIndex<=0" in body
    assert "playbackIndex>=playback.length-1" in body
    assert "${playbackIndex} / ${playback.length-1}" in body


def test_previous_and_next_steps_share_one_handler():
    html = source()
    assert html.count('id="historyPrev"') == 1
    assert html.count('id="historyNext"') == 1
    assert 'onclick="historyStep(-1)"' in html
    assert 'onclick="historyStep(1)"' in html
    assert "if(playback){playbackStep(delta);return}" in body_of_function("historyStep")


def test_playback_moves_cursor_without_replacing_timeline():
    body = body_of_function("playbackStep")
    assert "playbackIndex+direction" in body
    assert "playback[playbackIndex]" in body
    assert "renderPlayback()" in body
    assert "playback=" not in body


def test_engine_history_opens_at_end_and_is_not_reset():
    html = source()
    assert "openPlayback(r.timeline,'Рішення Stockfish — обидві сторони',r.warning,true)" in html
    assert "if(playbackBefore)playbackBefore.fen=r.timeline[r.timeline.length-1].fen" in html
    assert "openPlayback(r.timeline,'Історія партії зі Stockfish'" in html
