"""
main.py – точка входа ИАС Розничных продаж.

Запуск:
    python main.py           – графический интерфейс (tkinter)
    python main.py --cli     – консольный режим (без GUI)
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def run_gui():
    from gui import RetailIASApp
    app = RetailIASApp()
    app.mainloop()


def run_cli():
    """Консольный режим — для сред без дисплея."""
    from generate_data import generate_all
    from core import DataWarehouse, ETLProcessor, DataMart, AnalyticsEngine, DB_PATH
    from reports import ReportGenerator

    dw      = DataWarehouse(DB_PATH)
    etl     = ETLProcessor(dw)
    mart    = DataMart(dw)
    engine  = AnalyticsEngine(dw)
    reports = ReportGenerator(dw)
    dw.connect()

    menu = """
╔════════════════════════════════════════╗
║   ИАС Розничных продаж  (CLI-режим)   ║
╚════════════════════════════════════════╝
  1 – Генерировать тестовые данные
  2 – ETL: загрузить данные в БД
  3 – Построить витрину данных
  4 – ABC-анализ
  5 – XYZ-анализ
  6 – ABC-XYZ матрица
  7 – Динамика выручки по месяцам
  8 – Отчёт: выручка за квартал по городам
  9 – Отчёт: топ-10 товаров
  10 – Отчёт: топ-5 магазинов
  11 – Отчёт: поставщики
  12 – Проверка целостности
  0 – Выход
"""

    while True:
        print(menu)
        choice = input("Выберите действие: ").strip()

        if choice == "0":
            print("До свидания!")
            break

        elif choice == "1":
            print("Генерация данных…")
            generate_all()

        elif choice == "2":
            print("Запуск ETL…")
            dw.init_schema()
            log = etl.run()
            print("\n".join(log))

        elif choice == "3":
            print("Построение витрины…")
            msg = mart.build()
            print(msg)

        elif choice == "4":
            df = engine.abc_analysis()
            print("\nABC-анализ:")
            print(df.to_string(index=False))

        elif choice == "5":
            df = engine.xyz_analysis()
            print("\nXYZ-анализ:")
            print(df.to_string(index=False))

        elif choice == "6":
            df = engine.abcxyz_matrix()
            print("\nABC-XYZ матрица:")
            print(df[["product_name", "ABC", "XYZ", "ABC_XYZ", "revenue"]].to_string(index=False))

        elif choice == "7":
            cats = engine.get_categories()
            print("Категории:", ", ".join(cats))
            cat = input("Введите категорию (Enter = все): ").strip() or None
            df  = engine.revenue_by_month(cat)
            print(df.to_string(index=False))

        elif choice == "8":
            df  = reports.revenue_last_quarter()
            lbl = reports.last_quarter_label()
            print(f"\nВыручка за {lbl} по городам:")
            print(df.to_string(index=False))

        elif choice == "9":
            df = reports.top10_products()
            print("\nТоп-10 товаров:")
            print(df.to_string(index=False))

        elif choice == "10":
            df = reports.top5_stores_avg_check()
            print("\nТоп-5 магазинов по среднему чеку:")
            print(df.to_string(index=False))

        elif choice == "11":
            df = reports.supplier_report()
            print("\nОтчёт по поставщикам:")
            print(df.to_string(index=False))

        elif choice == "12":
            info = dw.integrity_check()
            print("\nПроверка целостности:")
            for tbl, d in info["details"].items():
                status = "OK" if d["exists"] else "ОТСУТСТВУЕТ"
                print(f"  {tbl}: {status}, строк: {d['rows']}")
            print(f"Контрольная сумма: {dw.checksum()}")
            print(f"Статус: {'OK' if info['ok'] else 'ОШИБКА'}")

        else:
            print("Неверный выбор. Попробуйте снова.")

    dw.close()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        try:
            run_gui()
        except Exception as e:
            print(f"GUI недоступен ({e}). Запуск в CLI-режиме.")
            run_cli()
