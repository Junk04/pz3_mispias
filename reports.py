"""
reports.py – генерация аналитических отчётов.
"""

from __future__ import annotations
import pandas as pd
from core import DataWarehouse


class ReportGenerator:
    """Формирует стандартные отчёты на основе хранилища данных."""

    def __init__(self, dw: DataWarehouse):
        self.dw = dw

    # ── 1. Выручка за последний квартал по городам ───────────
    def revenue_last_quarter(self) -> pd.DataFrame:
        sql = """
        WITH last_q AS (
            SELECT year, quarter
            FROM sales_mart
            ORDER BY year DESC, quarter DESC
            LIMIT 1
        )
        SELECT
            s.city,
            SUM(sm.total_revenue) AS revenue,
            SUM(sm.total_qty)     AS qty,
            SUM(sm.transactions)  AS transactions
        FROM sales_mart sm
        JOIN last_q lq ON sm.year = lq.year AND sm.quarter = lq.quarter
        JOIN (SELECT DISTINCT store_id, city FROM dim_store) s
            ON sm.store_id = s.store_id
        GROUP BY s.city
        ORDER BY revenue DESC;
        """
        df = self.dw.execute_df(sql)
        df["revenue"] = df["revenue"].round(2)
        return df

    def last_quarter_label(self) -> str:
        sql = "SELECT year, quarter FROM sales_mart ORDER BY year DESC, quarter DESC LIMIT 1;"
        row = self.dw.execute_df(sql)
        if row.empty:
            return "н/д"
        return f"{row.iloc[0]['year']} Q{row.iloc[0]['quarter']}"

    # ── 2. Топ-10 товаров по выручке ─────────────────────────
    def top10_products(self) -> pd.DataFrame:
        sql = """
        SELECT
            product_name,
            category,
            SUM(total_revenue) AS revenue,
            SUM(total_qty)     AS qty
        FROM sales_mart
        GROUP BY product_id, product_name, category
        ORDER BY revenue DESC
        LIMIT 10;
        """
        df = self.dw.execute_df(sql)
        df["revenue"] = df["revenue"].round(2)
        df.insert(0, "#", range(1, len(df) + 1))
        return df

    # ── 3. Топ-5 магазинов по среднему чеку ──────────────────
    def top5_stores_avg_check(self) -> pd.DataFrame:
        sql = """
        SELECT
            s.city,
            s.store_type,
            s.district,
            ROUND(AVG(sm.avg_check), 2) AS avg_check,
            SUM(sm.transactions)        AS transactions
        FROM sales_mart sm
        JOIN dim_store s ON sm.store_id = s.store_id
        GROUP BY sm.store_id, s.city, s.store_type, s.district
        ORDER BY avg_check DESC
        LIMIT 5;
        """
        df = self.dw.execute_df(sql)
        df.insert(0, "#", range(1, len(df) + 1))
        return df

    # ── 4. Отчёт по поставщикам ──────────────────────────────
    def supplier_report(self) -> pd.DataFrame:
        sql = """
        SELECT
            supplier,
            SUM(total_revenue) AS revenue,
            SUM(total_qty)     AS qty,
            COUNT(DISTINCT product_id) AS products
        FROM sales_mart
        GROUP BY supplier
        ORDER BY revenue DESC;
        """
        df = self.dw.execute_df(sql)
        df["revenue"] = df["revenue"].round(2)
        total = df["revenue"].sum()
        df["share_pct"] = (df["revenue"] / total * 100).round(2)
        df.insert(0, "#", range(1, len(df) + 1))
        return df
