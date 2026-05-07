"""
generate_data.py – генерация тестовых CSV-файлов для ИАС розничных продаж.
Создаёт: data/sales.csv, data/products.csv, data/stores.csv
"""

import os
import random
import csv
from datetime import date, timedelta

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ──────────────────────────────────────────────
# Справочники
# ──────────────────────────────────────────────
PRODUCTS = [
    (1,  "Смартфон Samsung Galaxy A54",  "Электроника",   "Samsung"),
    (2,  "Ноутбук Lenovo IdeaPad 3",     "Электроника",   "Lenovo"),
    (3,  "Наушники Sony WH-1000XM5",     "Электроника",   "Sony"),
    (4,  "Куртка зимняя Adidas",         "Одежда",        "Adidas"),
    (5,  "Кроссовки Nike Air Max",       "Одежда",        "Nike"),
    (6,  "Джинсы Levi's 501",            "Одежда",        "Levi's"),
    (7,  "Молоко Простоквашино 1л",      "Продукты",      "Данон"),
    (8,  "Хлеб пшеничный нарезной",      "Продукты",      "Коломенский"),
    (9,  "Кофе Jacobs Monarch 250г",     "Продукты",      "Jacobs"),
    (10, "Стиральный порошок Tide 3кг",  "Бытовая химия", "P&G"),
    (11, "Шампунь Head&Shoulders 400мл", "Бытовая химия", "P&G"),
    (12, "Планшет Apple iPad Air",       "Электроника",   "Apple"),
    (13, "Футболка базовая Uniqlo",      "Одежда",        "Uniqlo"),
    (14, "Сок Rich яблоко 1л",           "Продукты",      "Мултон"),
    (15, "Чай Lipton Yellow Label 100п", "Продукты",      "Unilever"),
]

STORES = [
    (1, "Москва",          "ЦАО",           "Гипермаркет"),
    (2, "Москва",          "ЮАО",           "Супермаркет"),
    (3, "Санкт-Петербург", "Центральный",   "Гипермаркет"),
    (4, "Санкт-Петербург", "Московский",    "Супермаркет"),
    (5, "Казань",          "Вахитовский",   "Супермаркет"),
    (6, "Новосибирск",     "Центральный",   "Минимаркет"),
    (7, "Екатеринбург",    "Верх-Исетский", "Минимаркет"),
    (8, "Москва",          "СВАО",          "Минимаркет"),
]

# Базовые цены товаров (руб.)
BASE_PRICES = {
    1: 29990, 2: 54990, 3: 24990, 4: 8990,  5: 9990,
    6: 3990,  7: 89,    8: 45,    9: 349,   10: 519,
    11: 299,  12: 64990, 13: 999,  14: 79,   15: 199,
}

# Веса популярности товаров (некоторые продаются чаще)
PRODUCT_WEIGHTS = {
    1: 4, 2: 2, 3: 3, 4: 5, 5: 6, 6: 4, 7: 10, 8: 12, 9: 8, 10: 7,
    11: 6, 12: 2, 13: 5, 14: 9, 15: 8,
}

# ──────────────────────────────────────────────
# Генерация продаж
# ──────────────────────────────────────────────
def generate_sales(n: int = 1500) -> list[dict]:
    start = date(2023, 1, 1)
    end   = date(2024, 12, 31)
    delta = (end - start).days

    product_ids = list(PRODUCT_WEIGHTS.keys())
    weights     = [PRODUCT_WEIGHTS[pid] for pid in product_ids]
    store_ids   = [s[0] for s in STORES]

    rows = []
    for i in range(1, n + 1):
        sale_date  = start + timedelta(days=random.randint(0, delta))
        product_id = random.choices(product_ids, weights=weights, k=1)[0]
        store_id   = random.choice(store_ids)
        quantity   = random.randint(1, 5) if product_id > 6 else random.randint(1, 2)
        # небольшой ценовой разброс ±5 %
        base  = BASE_PRICES[product_id]
        price = round(base * random.uniform(0.95, 1.05), 2)
        rows.append({
            "sale_id":    i,
            "date":       sale_date.strftime("%Y-%m-%d"),
            "product_id": product_id,
            "store_id":   store_id,
            "quantity":   quantity,
            "price":      price,
        })

    # Добавим несколько «грязных» строк для проверки ETL (пропуски)
    for _ in range(20):
        rows.append({
            "sale_id":    9000 + random.randint(1, 999),
            "date":       "",            # пустая дата
            "product_id": random.randint(1, 15),
            "store_id":   random.choice(store_ids),
            "quantity":   random.randint(1, 3),
            "price":      100.0,
        })
    for _ in range(10):
        rows.append({
            "sale_id":    8000 + random.randint(1, 999),
            "date":       "2024-06-15",
            "product_id": 999,           # несуществующий товар
            "store_id":   random.choice(store_ids),
            "quantity":   1,
            "price":      100.0,
        })

    random.shuffle(rows)
    return rows


def write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓ Записан: {path}  ({len(rows)} строк)")


def generate_all() -> None:
    print("Генерация тестовых данных…")

    # products.csv
    product_rows = [
        {"product_id": p[0], "product_name": p[1], "category": p[2], "supplier": p[3]}
        for p in PRODUCTS
    ]
    write_csv(
        os.path.join(DATA_DIR, "products.csv"),
        ["product_id", "product_name", "category", "supplier"],
        product_rows,
    )

    # stores.csv
    store_rows = [
        {"store_id": s[0], "city": s[1], "district": s[2], "store_type": s[3]}
        for s in STORES
    ]
    write_csv(
        os.path.join(DATA_DIR, "stores.csv"),
        ["store_id", "city", "district", "store_type"],
        store_rows,
    )

    # sales.csv
    sales_rows = generate_sales(1500)
    write_csv(
        os.path.join(DATA_DIR, "sales.csv"),
        ["sale_id", "date", "product_id", "store_id", "quantity", "price"],
        sales_rows,
    )

    print("Готово. Файлы в папке data/")


if __name__ == "__main__":
    generate_all()
