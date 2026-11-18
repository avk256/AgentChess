/* Regression checks for the 0.5.11 user-facing requirements. */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
const api=fs.readFileSync(path.join(__dirname,'../backend/app.py'),'utf8');
const exercise=fs.readFileSync(path.join(__dirname,'../backend/exercise04.py'),'utf8');
test('navigation remains visible directly below chessboard',()=>{
 assert.match(html,/<\/div><nav class="board-navigation"/);
 assert.match(html,/id="boardPrev" onclick="boardStep\(-1\)"/);
 assert.match(html,/id="boardNext" onclick="boardStep\(1\)"/);
 assert.match(html,/if\(solutionData\)\{solutionStep\(delta\)/);
 assert.match(html,/if\(playback\)\{playbackStep\(delta\)/);
});
test('defaults use contrast pieces and attacked-square highlighting',()=>{
 assert.match(html,/getItem\('agentchess_pieceStyle'\)\|\|'contrast'/);
 assert.match(html,/getItem\('agentchess_showAttacks'\)==='off'\?'off':'on'/);
});
test('finish and engine result retain last position and navigation',()=>{
 assert.match(html,/openPlayback\(exerciseTimeline,[^\n]*true\)/);
 assert.match(html,/openPlayback\(r.timeline,'Завершена партія зі Stockfish',null,true\)/);
 assert.match(html,/openPlayback\(r.timeline,'Рішення Stockfish — обидві сторони',r.warning,true\)/);
 assert.match(html,/playbackBefore.fen=r.timeline\[r.timeline.length-1\].fen/);
});
test('checkmate verified using python-chess and displayed on king square',()=>{
 assert.match(api,/board\.is_checkmate\(\)/);
 assert.match(api,/board\.king\(board\.turn\)/);
 assert.match(exercise,/after_move\.is_checkmate\(\)/);
 assert.match(html,/square\.classList\.toggle\('checkmated'/);
 assert.match(html,/\.square\.checkmated\{background:#f3a5aa!important/);
});
