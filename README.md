# AgentChess MVP 0.2 — CDB Import & Catalog

## Статус

- Перероблений імпортер єдиних 33 CDB-джерел (`vlasov.tar.gz`, 34 файли, SHA-256 дедуплікація).
- Вихідні SQLite-таблиці `games`, `contents`, `params` обробляються окремо.
- Збереження первинних даних, оригінального MoveText, FEN, Elo, класифікації, структури розділів та відношень між ними.
- `python-chess` використовує PGN parser (разом із деревами альтернатив) та перевірку FEN/легальності ходів, якщо залежність доступна.
- Конвертація: `records.jsonl` (JSON Lines), `positions.fen`, `games.pgn`, `source.json`, `chapters.json`, `conversion_report.json`, `validation_errors.csv` **на кожне джерело**.
- Вебкаталог (тема, статус, складність, пагінація) та FastAPI endpoints.
- Модель `cdb_exercises` з полями мети, дерева розв'язання та статусу незалежно від `cdb_records`.
- Жодна імпортована вправа не видається як перевірена без окремої предметної валідації (MVP 0.3).

## Системні вимоги (Xubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv stockfish unzip
```

Розпакуйте AgentChess_MVP_02.zip. Усередині каталогу `AgentChess_MVP_02`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Увага:** у пакеті є попередня база даних, побудована у середовищі БЕЗ python-chess, тому записи в ній позначені `PARSER_UNAVAILABLE`. Після встановлення залежностей **обов'язково** запустіть `--rebuild` для реальної валідації та PGN-експорту.

```bash
python backend/import_cli.py data/original/vlasov.tar.gz --rebuild
```

Ця команда видаляє ТІЛЬКИ раніше імпортований каталог (`cdb_sources`, розділи, записи, кандидати вправ) та імпортує його повторно. Акаунти й партії зберігаються. Вихідний архів не змінюється.

Запуск:

```bash
export AGENTCHESS_BOOTSTRAP_ADMIN=admin
export STOCKFISH_PATH=/usr/games/stockfish
./run.sh
```

Далі відкрийте `http://127.0.0.1:8000`. Зареєструйте користувача з іменем `admin` (перший запуск). Для звичайного акаунта достатньо зареєструвати інше ім'я. Для локального середовища використовуйте складний пароль. `AGENTCHESS_BOOTSTRAP_ADMIN` слід встановити до першої реєстрації адміністратора та прибрати для наступних запусків.

API: `http://127.0.0.1:8000/docs`. Статус: `GET /api/health`.

### CLI перевірки

```bash
python backend/import_cli.py data/original/vlasov.tar.gz
python backend/import_cli.py data/original/vlasov.tar.gz --rebuild
python -m pytest tests/ -q
```

Перший повторний імпорт ідемпотентний: імпортовані SHA-256 не дублюються.

### Приклади API

Авторизація: `POST /api/auth/register`, `POST /api/auth/login`, Bearer token.

- `GET /api/sources` — 33 джерела (назви й статистика)
- `GET /api/sources/{id}` — параметри та навігація по розділах
- `GET /api/catalog?topic=подвійний%20удар&limit=20&offset=0` — пошук
- `GET /api/catalog/{id}` — деталі (еталонні ходи приховано від неадміністраторів)
- `POST /api/imports` — імпорт `.cdb` або `.tar.gz`, лише адміністратор
- `GET /api/imports/{run_id}/report` — звіт, лише адміністратор
- `GET /api/games`, `POST /api/games`, `POST /api/games/{id}/moves` — ігровий прототип v0.1 (метод POST для створення)
- `GET /api/progress` — базова статистика з прототипу

## Архітектура каталогу

| Таблиця | Зміст |
|---|---|
| `cdb_sources` | Унікальне джерело SHA-256, параметри, звіт |
| `cdb_source_paths` | Усі розташування, включно з дублікатами |
| `cdb_chapters` | Ієрархія `contents` (`parent`, `gameid`) |
| `cdb_records` | 18 805 оригінальних записів, нормалізація, статус |
| `cdb_exercises` | Кандидати у вправи, мета, варіанти, статус готовності |
| `cdb_import_runs` | Історія імпорту і підсумкові звіти |

### Семантика статусів

- `PARSER_UNAVAILABLE`: шаховий парсер у середовищі імпорту відсутній.
- `INVALID_FEN`: `python-chess` виявив невалідну позицію.
- `PARSE_ERROR`: помилка розбору PGN або нелегальна послідовність.
- `EMPTY_MOVETEXT`: текст ходів порожній.
- `THEORY`: немає розпізнаних ходів; може бути поясненням.
- `LEGAL_MOVES`: python-chess розпізнав послідовність; **не підтверджує** правильності рішення задачі.

Готовність `cdb_exercises.readiness=REVIEW_REQUIRED` за замовчуванням. Статус `READY` у MVP 0.2 автоматично **не встановлюється**.

## Обмеження

1. У середовищі складання мережевий pip був недоступний, тому вже вкладені `games.pgn` та `positions.fen` поки порожні, а всі записи позначені `PARSER_UNAVAILABLE`. На Xubuntu після `pip install` і `--rebuild` файли генеруються.
2. PGN-парсер не гарантує коректність усіх нестандартних `MoveText`. Окремі файли `validation_errors.csv` слід аналізувати після `--rebuild`.
3. Авторські навчальні цілі та повнота матових дерев **не перевірені** — MVP 0.3.
4. База зараз SQLite для локального прототипування; PostgreSQL + міграції заплановані в наступних версіях.
5. Ігровий модуль — попередній v0.1 і не заявляється production-ready; локальний запуск рекомендовано тільки на `127.0.0.1`.
6. Оригінальні шахові джерела можуть містити матеріали, обмежені авторським правом. Не публікуйте архів і тексти без перевірки прав.
