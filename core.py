"""
core.py – основные компоненты ИАС розничных продаж.

Классы:
  ETLProcessor    – извлечение, преобразование, загрузка данных из CSV → SQLite
  DataWarehouse   – работа с реляционным хранилищем (SQLite)
  DataMart        – построение витрины данных
  AnalyticsEngine – ABC/XYZ-анализ, графики динамики выручки
"""

from __future__ import annotations

import os
import sqlite3
import hashlib
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

DB_PATH   = os.path.join(os.path.dirname(__file__), "data", "retail.db")
DATA_DIR  = os.path.join(os.path.dirname(__file__), "data")


# ══════════════════════════════════════════════════════════════
# DataWarehouse
# ══════════════════════════════════════════════════════════════
class DataWarehouse:
    """Управляет соединением с SQLite и схемой хранилища."""

    DDL_FACT = """
    CREATE TABLE IF NOT EXISTS fact_sales (
        sale_id    INTEGER PRIMARY KEY,
        date       TEXT    NOT NULL,
        year       INTEGER,
        month      INTEGER,
        quarter    INTEGER,
        product_id INTEGER,
        store_id   INTEGER,
        quantity   INTEGER,
        price      REAL,
        revenue    REAL,
        FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
        FOREIGN KEY (store_id)   REFERENCES dim_store(store_id)
    );"""

    DDL_DIM_PRODUCT = """
    CREATE TABLE IF NOT EXISTS dim_product (
        product_id   INTEGER PRIMARY KEY,
        product_name TEXT,
        category     TEXT,
        supplier     TEXT
    );"""

    DDL_DIM_STORE = """
    CREATE TABLE IF NOT EXISTS dim_store (
        store_id   INTEGER PRIMARY KEY,
        city       TEXT,
        district   TEXT,
        store_type TEXT
    );"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ── Соединение ──────────────────────────────────────────
    def connect(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ── Схема ───────────────────────────────────────────────
    def init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(self.DDL_DIM_PRODUCT)
        cur.execute(self.DDL_DIM_STORE)
        cur.execute(self.DDL_FACT)
        self.conn.commit()
        logger.info("Схема БД инициализирована.")

    def drop_all(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DROP TABLE IF EXISTS sales_mart;")
        cur.execute("DROP TABLE IF EXISTS fact_sales;")
        cur.execute("DROP TABLE IF EXISTS dim_product;")
        cur.execute("DROP TABLE IF EXISTS dim_store;")
        self.conn.commit()
        logger.info("Все таблицы удалены.")

    # ── Проверка целостности ─────────────────────────────────
    def integrity_check(self) -> dict:
        """Проверяет наличие таблиц и количество записей."""
        required = ["dim_product", "dim_store", "fact_sales"]
        result = {"ok": True, "details": {}}
        cur = self.conn.cursor()
        for tbl in required:
            cur.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?;",
                (tbl,),
            )
            exists = cur.fetchone()[0] > 0
            count  = 0
            if exists:
                cur.execute(f"SELECT COUNT(*) FROM {tbl};")
                count = cur.fetchone()[0]
            result["details"][tbl] = {"exists": exists, "rows": count}
            if not exists:
                result["ok"] = False
        return result

    # ── Хелперы ─────────────────────────────────────────────
    def execute_df(self, sql: str, params=()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.conn, params=params)

    def bulk_insert(self, table: str, df: pd.DataFrame) -> None:
        df.to_sql(table, self.conn, if_exists="append", index=False)

    def checksum(self) -> str:
        """Простая «контрольная сумма» хранилища (кол-во строк в таблицах)."""
        info = self.integrity_check()
        raw  = str(info["details"])
        return hashlib.md5(raw.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════
# ETLProcessor
# ══════════════════════════════════════════════════════════════
class ETLProcessor:
    """Загружает, преобразует и сохраняет данные из CSV в хранилище."""

    def __init__(self, dw: DataWarehouse, data_dir: str = DATA_DIR):
        self.dw       = dw
        self.data_dir = data_dir
        self.log: list[str] = []

    def _path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    # ── Extract ─────────────────────────────────────────────
    def extract(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        self.log.clear()
        required = {"sales.csv", "products.csv", "stores.csv"}
        missing  = [f for f in required if not os.path.exists(self._path(f))]
        if missing:
            raise FileNotFoundError(
                f"Не найдены файлы: {', '.join(missing)}\n"
                f"Запустите «Генерация данных» или поместите CSV в папку data/."
            )

        sales    = pd.read_csv(self._path("sales.csv"),    dtype=str)
        products = pd.read_csv(self._path("products.csv"), dtype=str)
        stores   = pd.read_csv(self._path("stores.csv"),   dtype=str)

        self.log.append(f"Извлечено продаж:  {len(sales)}")
        self.log.append(f"Извлечено товаров: {len(products)}")
        self.log.append(f"Извлечено магазинов: {len(stores)}")
        return sales, products, stores

    # ── Transform ────────────────────────────────────────────
    def transform(
        self,
        sales: pd.DataFrame,
        products: pd.DataFrame,
        stores: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:

        init_rows = len(sales)

        # 1. Удаление пропусков критических полей
        critical = ["date", "product_id", "store_id", "quantity", "price"]
        sales = sales.dropna(subset=critical)
        sales = sales[sales[critical].apply(lambda c: c.str.strip() != "").all(axis=1)]
        self.log.append(f"Удалено строк с пропусками: {init_rows - len(sales)}")

        # 2. Приведение типов
        sales["date"]       = pd.to_datetime(sales["date"], format="%Y-%m-%d", errors="coerce")
        sales               = sales.dropna(subset=["date"])
        sales["product_id"] = pd.to_numeric(sales["product_id"], errors="coerce").astype("Int64")
        sales["store_id"]   = pd.to_numeric(sales["store_id"],   errors="coerce").astype("Int64")
        sales["quantity"]   = pd.to_numeric(sales["quantity"],   errors="coerce").astype("Int64")
        sales["price"]      = pd.to_numeric(sales["price"],      errors="coerce")
        sales               = sales.dropna(subset=["product_id", "store_id", "quantity", "price"])

        products["product_id"] = pd.to_numeric(products["product_id"], errors="coerce").astype("Int64")
        stores["store_id"]     = pd.to_numeric(stores["store_id"],     errors="coerce").astype("Int64")

        # 3. Проверка ссылочной целостности
        valid_products = set(products["product_id"].dropna())
        valid_stores   = set(stores["store_id"].dropna())
        before = len(sales)
        sales  = sales[sales["product_id"].isin(valid_products) & sales["store_id"].isin(valid_stores)]
        self.log.append(f"Удалено строк (нарушение целостности): {before - len(sales)}")

        # 4. Вычисление revenue, year, month, quarter
        sales["revenue"] = (sales["quantity"] * sales["price"]).round(2)
        sales["year"]    = sales["date"].dt.year
        sales["month"]   = sales["date"].dt.month
        sales["quarter"] = sales["date"].dt.quarter
        sales["date"]    = sales["date"].dt.strftime("%Y-%m-%d")

        # 5. Приведение ID к обычному int для sqlite
        for col in ["product_id", "store_id", "quantity", "year", "month", "quarter"]:
            sales[col] = sales[col].astype(int)

        self.log.append(f"Итого корректных записей продаж: {len(sales)}")
        self.log.append(f"Товаров в справочнике: {len(products)}")
        self.log.append(f"Магазинов в справочнике: {len(stores)}")

        # sale_id
        if "sale_id" in sales.columns:
            sales["sale_id"] = pd.to_numeric(sales["sale_id"], errors="coerce").astype("Int64").astype(int)
        else:
            sales.insert(0, "sale_id", range(1, len(sales) + 1))

        return sales, products, stores

    # ── Load ─────────────────────────────────────────────────
    def load(
        self,
        sales: pd.DataFrame,
        products: pd.DataFrame,
        stores: pd.DataFrame,
    ) -> None:
        conn = self.dw.conn
        # Создаём резервные таблицы для возможного отката
        backup_created = False
        try:
            # Создаём резервные копии существующих данных
            for tbl in ("fact_sales", "dim_product", "dim_store"):
                conn.execute(f"DROP TABLE IF EXISTS {tbl}_bak;")
                conn.execute(f"CREATE TABLE {tbl}_bak AS SELECT * FROM {tbl};")
            conn.commit()
            backup_created = True

            # Очистка таблиц
            conn.execute("DELETE FROM fact_sales;")
            conn.execute("DELETE FROM dim_product;")
            conn.execute("DELETE FROM dim_store;")
            conn.commit()

            product_cols = ["product_id", "product_name", "category", "supplier"]
            products[product_cols].to_sql("dim_product", conn, if_exists="append", index=False)

            store_cols = ["store_id", "city", "district", "store_type"]
            stores[store_cols].to_sql("dim_store", conn, if_exists="append", index=False)

            fact_cols = ["sale_id", "date", "year", "month", "quarter",
                         "product_id", "store_id", "quantity", "price", "revenue"]
            sales[fact_cols].to_sql("fact_sales", conn, if_exists="append", index=False)

            # Удаляем резервные копии
            for tbl in ("fact_sales", "dim_product", "dim_store"):
                conn.execute(f"DROP TABLE IF EXISTS {tbl}_bak;")
            conn.commit()
            self.log.append("Данные успешно загружены в хранилище.")

        except Exception as exc:
            logger.error("ETL Load Error: %s", exc)
            # Откат из резервных копий
            if backup_created:
                try:
                    for tbl in ("fact_sales", "dim_product", "dim_store"):
                        conn.execute(f"DELETE FROM {tbl};")
                        conn.execute(f"INSERT INTO {tbl} SELECT * FROM {tbl}_bak;")
                        conn.execute(f"DROP TABLE IF EXISTS {tbl}_bak;")
                    conn.commit()
                    logger.info("Данные восстановлены из резервных копий.")
                except Exception as rb_exc:
                    logger.error("Ошибка отката: %s", rb_exc)
            raise RuntimeError(f"Ошибка загрузки данных: {exc}")

    # ── Публичный метод ──────────────────────────────────────
    def run(self) -> list[str]:
        """Полный ETL-процесс. Возвращает лог операций."""
        self.dw.init_schema()
        sales, products, stores = self.extract()
        sales, products, stores = self.transform(sales, products, stores)
        self.load(sales, products, stores)
        return self.log


# ══════════════════════════════════════════════════════════════
# DataMart
# ══════════════════════════════════════════════════════════════
class DataMart:
    """Строит агрегированную витрину данных sales_mart."""

    CREATE_MART = """
    CREATE TABLE IF NOT EXISTS sales_mart AS
    SELECT
        f.year,
        f.quarter,
        f.month,
        p.category,
        p.supplier,
        p.product_id,
        p.product_name,
        s.city,
        s.store_type,
        s.store_id,
        SUM(f.quantity)           AS total_qty,
        SUM(f.revenue)            AS total_revenue,
        ROUND(AVG(f.revenue), 2)  AS avg_check,
        COUNT(f.sale_id)          AS transactions
    FROM fact_sales f
    JOIN dim_product p ON f.product_id = p.product_id
    JOIN dim_store   s ON f.store_id   = s.store_id
    GROUP BY
        f.year, f.quarter, f.month,
        p.category, p.supplier, p.product_id, p.product_name,
        s.city, s.store_type, s.store_id;
    """

    def __init__(self, dw: DataWarehouse):
        self.dw = dw

    def build(self) -> str:
        conn = self.dw.conn
        try:
            conn.execute("DROP TABLE IF EXISTS sales_mart;")
            conn.execute(self.CREATE_MART)
            conn.commit()
            cur = conn.execute("SELECT COUNT(*) FROM sales_mart;")
            n = cur.fetchone()[0]
            return f"Витрина sales_mart построена. Строк: {n}."
        except Exception as exc:
            conn.rollback()
            raise RuntimeError(f"Ошибка построения витрины: {exc}")

    def get_mart(self) -> pd.DataFrame:
        return self.dw.execute_df("SELECT * FROM sales_mart;")


# ══════════════════════════════════════════════════════════════
# AnalyticsEngine
# ══════════════════════════════════════════════════════════════
class AnalyticsEngine:
    """ABC/XYZ-анализ и прочая аналитика на основе витрины данных."""

    def __init__(self, dw: DataWarehouse):
        self.dw = dw

    # ── ABC-анализ ───────────────────────────────────────────
    def abc_analysis(self) -> pd.DataFrame:
        sql = """
        SELECT product_id, product_name, SUM(total_revenue) AS revenue
        FROM sales_mart
        GROUP BY product_id, product_name
        ORDER BY revenue DESC;
        """
        df = self.dw.execute_df(sql)
        if df.empty:
            raise RuntimeError("Витрина данных пуста. Сначала постройте витрину.")

        df["cumulative_pct"] = df["revenue"].cumsum() / df["revenue"].sum() * 100
        conditions = [
            df["cumulative_pct"] <= 80,
            df["cumulative_pct"] <= 95,
        ]
        df["ABC"] = np.select(conditions, ["A", "B"], default="C")
        df["revenue"] = df["revenue"].round(2)
        df["cumulative_pct"] = df["cumulative_pct"].round(2)
        return df

    # ── XYZ-анализ ───────────────────────────────────────────
    def xyz_analysis(self) -> pd.DataFrame:
        sql = """
        SELECT product_id, product_name, year, month, SUM(total_qty) AS qty
        FROM sales_mart
        GROUP BY product_id, product_name, year, month;
        """
        df = self.dw.execute_df(sql)
        if df.empty:
            raise RuntimeError("Витрина данных пуста. Сначала постройте витрину.")

        def cv(series: pd.Series) -> float:
            m = series.mean()
            return (series.std() / m * 100) if m > 0 else 0.0

        xyz = (
            df.groupby(["product_id", "product_name"])["qty"]
            .apply(cv)
            .reset_index()
            .rename(columns={"qty": "cv_pct"})
        )
        xyz["cv_pct"] = xyz["cv_pct"].round(2)
        conditions = [xyz["cv_pct"] <= 10, xyz["cv_pct"] <= 25]
        xyz["XYZ"]  = np.select(conditions, ["X", "Y"], default="Z")
        return xyz

    # ── ABC-XYZ матрица ──────────────────────────────────────
    def abcxyz_matrix(self) -> pd.DataFrame:
        abc = self.abc_analysis()[["product_id", "product_name", "revenue", "ABC"]]
        xyz = self.xyz_analysis()[["product_id", "XYZ", "cv_pct"]]
        merged = abc.merge(xyz, on="product_id")
        merged["ABC_XYZ"] = merged["ABC"] + merged["XYZ"]
        return merged

    # ── Динамика выручки по месяцам ──────────────────────────
    def revenue_by_month(self, category: Optional[str] = None) -> pd.DataFrame:
        if category:
            sql = """
            SELECT year, month, SUM(total_revenue) AS revenue
            FROM sales_mart
            WHERE category = ?
            GROUP BY year, month
            ORDER BY year, month;
            """
            df = self.dw.execute_df(sql, params=(category,))
        else:
            sql = """
            SELECT year, month, SUM(total_revenue) AS revenue
            FROM sales_mart
            GROUP BY year, month
            ORDER BY year, month;
            """
            df = self.dw.execute_df(sql)

        df["period"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
        df["revenue"] = df["revenue"].round(2)
        return df

    # ── Список категорий ─────────────────────────────────────
    def get_categories(self) -> list[str]:
        df = self.dw.execute_df("SELECT DISTINCT category FROM sales_mart ORDER BY category;")
        return df["category"].tolist()
