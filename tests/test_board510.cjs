/* MVP 0.5.10 – dependency-free JavaScript regression tests. Run: node --test tests/test_board510.cjs */
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,'JS script missing');
const fake={addEventListener(){},querySelectorAll(){return []},classList:{add(){},remove(){}},options:[],value:''};
const ctx=vm.createContext({document:{getElementById(){return fake}},window:{addEventListener(){}},console,setTimeout,clearTimeout,Promise,URLSearchParams,localStorage:{getItem(){return null},setItem(){}}});
vm.runInContext(script.replace(/loadUiTheme\(\);loadAppearance\(\);loadMoveOptions\(\);loadDrawer\(\);setBoardFeedback\('idle'\);render\(\);filtersChanged\(\);if\(token\)[\s\S]*$/,''),ctx);
const calc=(expr)=>vm.runInContext(expr,ctx);
const arr=x=>Array.from(x);

test('board supports pointer drag and animation controls',()=>{
 assert.match(html,/onpointerdown=e=>startDrag/);
 assert.match(html,/pointerup.*draggingEnd/);
 assert.match(html,/id="animationSpeed"/);
 assert.match(html,/id="showAttacks"/);
 assert.match(html,/\.square\.last-from/);
 assert.match(html,/\.square\.attacked/);
 assert.match(html,/\.floating-piece/);
});
test('pawn attacks both diagonals, including empty squares',()=>{
 assert.deepEqual(arr(calc("attackedBy('e4','P',decode('start'))")),['d5','f5']);
 assert.deepEqual(arr(calc("attackedBy('f5','p',decode('start'))")),['e4','g4']);
});
test('knight attacks valid squares and obeys edges',()=>{
 assert.equal(calc("attackedBy('a1','N',decode('start')).length"),2);
 assert.deepEqual(new Set(arr(calc("attackedBy('a1','N',decode('start'))"))),new Set(['b3','c2']));
});
test('sliding attack stops at first occupied square',()=>{
 assert.deepEqual(arr(calc("attackedBy('a1','R',decode('start'))")),['a2','b1']);
});
test('move simulator handles ordinary move and side to move',()=>{
 const fen=calc("positionAfterUci('start','e2e4')");
 assert.ok(fen.includes(' b KQkq e3 0 1'));
 assert.equal(fen.split(' ')[0],'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR');
});
test('move simulator handles castling with rook move',()=>{
 const fen=calc("positionAfterUci('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','e1g1')");
 assert.ok(fen.startsWith('r3k2r/8/8/8/8/8/8/R4RK1 b kq -'));
});
test('move simulator handles en passant and promotion',()=>{
 const ep=calc("positionAfterUci('8/8/8/3pP3/8/8/8/4K2k w - d6 0 1','e5d6')");
 assert.equal(ep.split(' ')[0],'8/8/3P4/8/8/8/8/4K2k');
 const prom=calc("positionAfterUci('8/P7/8/8/8/8/8/4K2k w - - 0 1','a7a8q')");
 assert.equal(prom.split(' ')[0],'Q7/8/8/8/8/8/8/4K2k');
});
test('original CDB #3041 classification is not changed by this patch',()=>{
 assert.doesNotMatch(html,/mate_in_from_event|autoMateCorrection/);
});
