import csv
from collections import Counter
from pathlib import Path

root = Path("data/converted")

all_errors = []
types = Counter()
sources = Counter()

for file in root.rglob("validation_errors.csv"):
    with file.open(
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:
            row["source_dir"] = file.parent.name
            all_errors.append(row)

            # Категоризація за текстом повідомлення
            message = str(row.get("error", ""))

            types[message] += 1
            sources[file.parent.name] += 1

print("Загальна кількість повідомлень:", len(all_errors))

print("\nДжерела з найбільшою кількістю помилок:")

for name, count in sources.most_common(15):
    print(f"{name}: {count}")

print("\nНайпоширеніші повідомлення:")

for message, count in types.most_common(20):
    print(f"{count}: {message[:180]}")