# AgentChess MVP 0.5.12 — виправлення навігації

Це **інкрементальне оновлення поверх MVP 0.5.11**. У пакеті немає бази даних.

## Зміни

- Перенесено **робочу** панель «Історія ходів» (`playbackPanel`) із правої колонки під шахівницю.
- Вилучено дубльовані стрілки `boardPrev` / `boardNext` з окремою логікою `boardStep`.
- Постійна пара стрілок під дошкою використовує історію `playbackStep` для ручної задачі та режимів Stockfish.
- При перегляді активної історії кнопка «Повернутися до останньої позиції» повертає поточну ігрову позицію.
- Перевірки регресій реалізовано в `pytest` (`tests/test_board512.py`).

## Встановлення в Xubuntu

Зупиніть запущений локальний AgentChess (Ctrl+C), активуйте звичне Conda-середовище та перейдіть до кореня проєкту.

```bash
conda activate agentchess
cd /шлях/до/AgentChess_MVP_05_5
cp frontend/index.html frontend/index_before_0512.html
mkdir -p /tmp/agentchess0512
tar -xzf ~/Downloads/AgentChess_MVP_05_12_update.tar.gz -C /tmp/agentchess0512
cp /tmp/agentchess0512/frontend/index.html frontend/index.html
cp /tmp/agentchess0512/tests/test_board512.py tests/test_board512.py
python -m pytest tests/test_board512.py -q
python -m pytest tests/ -q
export STOCKFISH_PATH=/usr/games/stockfish
./run.sh
```

У Firefox натисніть Ctrl+Shift+R, щоб оновити кеш.

Тестування: під час ручного розв'язування ходів перегляньте попередні; після завершення задачі перевірте перемикання стрілками; повторіть із «Дограти зі Stockfish» та «Stockfish розв'язує». Перевірте повернення до останньої позиції.
