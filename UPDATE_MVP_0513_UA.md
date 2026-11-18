# AgentChess MVP 0.5.13 — виправлення навігації історією

## Причина помилки

У `animateUciSequence()` під час анімації встановлюється `moveBusy=true`.
Функція `render()` викликає `refreshBoardNavigation()`, тому під час анімації
кнопки ◀ ▶ вимикаються. Після анімації `moveBusy` скидався у `false`, але
стан кнопок **не оновлювався**. Тому після першого переходу назад стрілки
залишалися неактивними.

## Виправлення

У блоці `finally` функції `animateUciSequence()` після `moveBusy=false`
викликається `refreshBoardNavigation()`. У такий спосіб кнопки відображають
актуальну позицію `playbackIndex` після завершення анімації, а не проміжний
стан блокування. Для історії Stockfish та ручних задач використовується
спільна панель під дошкою.

## Склад пакета

- `frontend/index.html` — одне виправлення анімації/навігації;
- `tests/test_board513.py` — п'ять регресійних pytest-перевірок;
- `UPDATE_MVP_0513_UA.md` — цей файл.

Пакет встановлюється **поверх MVP 0.5.12**. Не змінює бекенд або базу даних.

## Локальне встановлення

```bash
conda activate agentchess
cd ~/kafedra/Chess/chess_agent/AgentChess_MVP_05_5
# Перед встановленням зупиніть ./run.sh через Ctrl+C
cp frontend/index.html frontend/index_before_0513.html
mkdir -p /tmp/agentchess0513
tar -xzf ~/Downloads/AgentChess_MVP_05_13_update.tar.gz -C /tmp/agentchess0513
cp /tmp/agentchess0513/frontend/index.html frontend/
cp /tmp/agentchess0513/tests/test_board513.py tests/
python -m pytest tests/test_board513.py -v
python -m pytest tests/ -q
export STOCKFISH_PATH=/usr/games/stockfish
./run.sh
```

Відкрийте застосунок у Firefox і натисніть **Ctrl+Shift+R**.
Перевірте послідовність `7/7 → 6/7 → 5/7 → … → 0/7 → … → 7/7` після
«Stockfish розв'язує», а також після «Дограти зі Stockfish» та ручного
розв'язання задачі. Під час анімації стрілки короткочасно неактивні; після
її завершення вони автоматично стають доступними відповідно до позиції.
