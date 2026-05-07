"""
gui.py – графический интерфейс ИАС розничных продаж (tkinter).

Структура окна:
  ┌─────────────────────────────────────────────────────┐
  │  Меню (Файл | Режимы | Отчёты | Справка)            │
  ├─────────────────────────────────────────────────────┤
  │  Панель вкладок (Notebook)                          │
  │  ┌──────┬───────────┬──────────┬──────────┬───────┐ │
  │  │ ETL  │  Витрина  │Аналитика │  Отчёты  │Справка│ │
  │  └──────┴───────────┴──────────┴──────────┴───────┘ │
  │  Область содержимого вкладки                        │
  ├─────────────────────────────────────────────────────┤
  │  Строка состояния                                   │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import seaborn as sns
import pandas as pd
import numpy as np

# Добавляем директорию проекта в sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from generate_data import generate_all
from core import DataWarehouse, ETLProcessor, DataMart, AnalyticsEngine, DB_PATH
from reports import ReportGenerator


# ══════════════════════════════════════════════════════════════
# Вспомогательные виджеты
# ══════════════════════════════════════════════════════════════
FONT_MAIN  = ("Segoe UI", 10)
FONT_TITLE = ("Segoe UI", 12, "bold")
COLOR_BG   = "#F5F6FA"
COLOR_BTN  = "#4A90D9"
COLOR_BTN_FG = "white"
COLOR_ACCENT = "#2C3E6B"

def make_btn(parent, text, command, width=22):
    return tk.Button(
        parent, text=text, command=command,
        bg=COLOR_BTN, fg=COLOR_BTN_FG, font=FONT_MAIN,
        relief="flat", padx=8, pady=4, width=width,
        activebackground="#2E6DB4", activeforeground="white", cursor="hand2",
    )

def make_label(parent, text, **kw):
    return tk.Label(parent, text=text, bg=COLOR_BG, font=FONT_MAIN, **kw)


class TreeviewFrame(ttk.Frame):
    """Фрейм с таблицей Treeview + горизонтальная и вертикальная прокрутка."""

    def __init__(self, parent, columns: list[str], **kw):
        super().__init__(parent, **kw)
        self.columns = columns
        self._build()

    def _build(self):
        vsb = ttk.Scrollbar(self, orient="vertical")
        hsb = ttk.Scrollbar(self, orient="horizontal")
        self.tree = ttk.Treeview(
            self, columns=self.columns, show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
            selectmode="browse",
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        for col in self.columns:
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=120, anchor="w", stretch=True)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def load(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        # Пересоздать столбцы если df изменился
        cols = list(df.columns)
        self.tree["columns"] = cols
        for col in cols:
            self.tree.heading(col, text=col, anchor="w")
            self.tree.column(col, width=max(80, len(col) * 9), anchor="w", stretch=True)
        for _, row in df.iterrows():
            vals = [str(v) for v in row]
            self.tree.insert("", "end", values=vals)


# ══════════════════════════════════════════════════════════════
# Главное приложение
# ══════════════════════════════════════════════════════════════
class RetailIASApp(tk.Tk):

    APP_TITLE   = "ИАС Розничных продаж"
    APP_VERSION = "1.0"
    AUTHOR      = "Шумкин Александр Юрьевич"
    GROUP       = "БИСО-03-23"
    APP_DATE    = "2026"

    def __init__(self):
        super().__init__()
        self.title(self.APP_TITLE)
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        # Компоненты ИАС
        self.dw      = DataWarehouse(DB_PATH)
        self.etl     = ETLProcessor(self.dw)
        self.mart    = DataMart(self.dw)
        self.engine  = AnalyticsEngine(self.dw)
        self.reports = ReportGenerator(self.dw)

        self.dw.connect()

        self._build_menu()
        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        self._set_status("Готово. Выберите действие.")

    # ── Меню ────────────────────────────────────────────────
    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Файл
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Генерировать тестовые данные", command=self._gen_data)
        m_file.add_separator()
        m_file.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=m_file)

        # Режимы
        m_modes = tk.Menu(menubar, tearoff=0)
        m_modes.add_command(label="1. ETL – загрузка данных",      command=lambda: self._switch_tab(0))
        m_modes.add_command(label="2. Витрина данных",             command=lambda: self._switch_tab(1))
        m_modes.add_command(label="3. Аналитика (ABC/XYZ)",        command=lambda: self._switch_tab(2))
        m_modes.add_command(label="4. Отчёты",                     command=lambda: self._switch_tab(3))
        menubar.add_cascade(label="Режимы", menu=m_modes)

        # Отчёты
        m_rep = tk.Menu(menubar, tearoff=0)
        m_rep.add_command(label="Выручка за последний квартал", command=self._report_quarter)
        m_rep.add_command(label="Топ-10 товаров",               command=self._report_top10)
        m_rep.add_command(label="Топ-5 магазинов",              command=self._report_top5)
        m_rep.add_command(label="Поставщики",                   command=self._report_suppliers)
        menubar.add_cascade(label="Отчёты", menu=m_rep)

        # Справка
        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="О программе",          command=self._about)
        m_help.add_command(label="Руководство пользователя", command=self._user_guide)
        menubar.add_cascade(label="Справка", menu=m_help)

    def _switch_tab(self, idx: int):
        self.nb.select(idx)

    # ── Заголовок ───────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=COLOR_ACCENT, height=48)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text=f"  🛒  {self.APP_TITLE}",
            bg=COLOR_ACCENT, fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=10, pady=8)

    # ── Notebook (вкладки) ───────────────────────────────────
    def _build_notebook(self):
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=FONT_MAIN, padding=[10, 5])

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        self.tab_etl       = self._build_tab_etl()
        self.tab_mart      = self._build_tab_mart()
        self.tab_analytics = self._build_tab_analytics()
        self.tab_reports   = self._build_tab_reports()
        self.tab_help      = self._build_tab_help()

        self.nb.add(self.tab_etl,       text="  📥 ETL  ")
        self.nb.add(self.tab_mart,      text="  🗃 Витрина  ")
        self.nb.add(self.tab_analytics, text="  📊 Аналитика  ")
        self.nb.add(self.tab_reports,   text="  📋 Отчёты  ")
        self.nb.add(self.tab_help,      text="  ℹ️ Справка  ")

    # ── Строка состояния ─────────────────────────────────────
    def _build_statusbar(self):
        self._status_var = tk.StringVar(value="Готово")
        bar = tk.Label(
            self, textvariable=self._status_var,
            bg="#D0D7E8", anchor="w", font=("Segoe UI", 9),
            relief="sunken", padx=6,
        )
        bar.pack(fill="x", side="bottom")

    def _set_status(self, msg: str):
        self._status_var.set(f"  {msg}")
        self.update_idletasks()

    # ══════════════════════════════════════════════════════════
    # Вкладка 1: ETL
    # ══════════════════════════════════════════════════════════
    def _build_tab_etl(self) -> tk.Frame:
        tab = tk.Frame(self.nb, bg=COLOR_BG)

        left = tk.Frame(tab, bg=COLOR_BG, width=220)
        left.pack(side="left", fill="y", padx=12, pady=12)
        left.pack_propagate(False)

        tk.Label(left, text="Режим 1: ETL", bg=COLOR_BG,
                 font=FONT_TITLE, fg=COLOR_ACCENT).pack(pady=(0, 10))

        make_btn(left, "📂 Генерировать CSV-данные", self._gen_data).pack(pady=4)
        make_btn(left, "▶  Запустить ETL",           self._run_etl).pack(pady=4)
        make_btn(left, "🔍 Проверка целостности",     self._check_integrity).pack(pady=4)
        make_btn(left, "🗑 Сбросить хранилище",       self._drop_db).pack(pady=4)

        # Лог
        tk.Label(left, text="Лог ETL:", bg=COLOR_BG, font=FONT_MAIN).pack(pady=(16, 2), anchor="w")
        self.etl_log = scrolledtext.ScrolledText(
            left, width=26, height=14, font=("Consolas", 9),
            state="disabled", wrap="word",
        )
        self.etl_log.pack(fill="both", expand=True)

        # Таблица факт-продаж (правая часть)
        right = tk.Frame(tab, bg=COLOR_BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=12)

        tk.Label(right, text="Таблица fact_sales (первые 500 строк)",
                 bg=COLOR_BG, font=FONT_TITLE, fg=COLOR_ACCENT).pack(pady=(0, 4))

        cols = ["sale_id", "date", "year", "month", "quarter",
                "product_id", "store_id", "quantity", "price", "revenue"]
        self.etl_tree = TreeviewFrame(right, columns=cols)
        self.etl_tree.pack(fill="both", expand=True)

        return tab

    def _gen_data(self):
        def task():
            try:
                self._set_status("Генерация тестовых данных…")
                generate_all()
                self._set_status("Тестовые данные сгенерированы в папку data/.")
                messagebox.showinfo("Генерация данных",
                                    "CSV-файлы успешно созданы в папке data/.\n"
                                    "Теперь запустите ETL.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
                self._set_status("Ошибка генерации данных.")
        threading.Thread(target=task, daemon=True).start()

    def _run_etl(self):
        def task():
            try:
                self._set_status("ETL: выполняется…")
                self._etl_log_clear()
                self.dw.init_schema()
                log = self.etl.run()
                for line in log:
                    self._etl_log_append(f"✓ {line}")
                # Показать данные
                df = self.dw.execute_df("SELECT * FROM fact_sales LIMIT 500;")
                self.after(0, lambda: self.etl_tree.load(df))
                self._set_status(f"ETL завершён. Загружено строк: {len(df)}.")
            except FileNotFoundError as e:
                messagebox.showwarning("Файлы не найдены", str(e))
                self._set_status("ETL прерван: файлы не найдены.")
            except Exception as e:
                messagebox.showerror("Ошибка ETL", str(e))
                self._set_status("ETL завершился с ошибкой.")
        threading.Thread(target=task, daemon=True).start()

    def _check_integrity(self):
        try:
            info = self.dw.integrity_check()
            lines = ["Проверка целостности хранилища:\n"]
            for tbl, d in info["details"].items():
                status = "✓" if d["exists"] else "✗"
                lines.append(f"  {status} {tbl}: {d['rows']} строк")
            lines.append(f"\nКонтрольная сумма: {self.dw.checksum()}")
            lines.append(f"\nСтатус: {'OK' if info['ok'] else 'ОШИБКА'}")
            messagebox.showinfo("Целостность хранилища", "\n".join(lines))
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _drop_db(self):
        if messagebox.askyesno("Сброс хранилища",
                               "Удалить все таблицы из БД?\nЭто действие необратимо."):
            try:
                self.dw.drop_all()
                self._set_status("Хранилище сброшено.")
                messagebox.showinfo("Сброс", "Все таблицы удалены.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def _etl_log_clear(self):
        self.etl_log.config(state="normal")
        self.etl_log.delete("1.0", "end")
        self.etl_log.config(state="disabled")

    def _etl_log_append(self, text: str):
        def _do():
            self.etl_log.config(state="normal")
            self.etl_log.insert("end", text + "\n")
            self.etl_log.see("end")
            self.etl_log.config(state="disabled")
        self.after(0, _do)

    # ══════════════════════════════════════════════════════════
    # Вкладка 2: Витрина
    # ══════════════════════════════════════════════════════════
    def _build_tab_mart(self) -> tk.Frame:
        tab = tk.Frame(self.nb, bg=COLOR_BG)

        top = tk.Frame(tab, bg=COLOR_BG)
        top.pack(fill="x", padx=12, pady=10)

        tk.Label(top, text="Режим 2: Витрина данных (sales_mart)",
                 bg=COLOR_BG, font=FONT_TITLE, fg=COLOR_ACCENT).pack(side="left")
        make_btn(top, "⚙ Построить витрину", self._build_mart, width=20).pack(side="right")
        make_btn(top, "🔄 Обновить таблицу", self._refresh_mart, width=20).pack(side="right", padx=4)

        self.mart_info = tk.Label(tab, text="", bg=COLOR_BG, font=FONT_MAIN, fg="#555")
        self.mart_info.pack(padx=12, anchor="w")

        self.mart_tree = TreeviewFrame(tab, columns=[])
        self.mart_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        return tab

    def _build_mart(self):
        def task():
            try:
                self._set_status("Построение витрины…")
                msg = self.mart.build()
                self._set_status(msg)
                self.after(0, lambda: self.mart_info.config(text=msg))
                self._refresh_mart()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
                self._set_status("Ошибка построения витрины.")
        threading.Thread(target=task, daemon=True).start()

    def _refresh_mart(self):
        try:
            df = self.mart.get_mart()
            self.mart_tree.load(df)
            self._set_status(f"Витрина: {len(df)} строк.")
        except Exception as e:
            self._set_status(f"Витрина недоступна: {e}")

    # ══════════════════════════════════════════════════════════
    # Вкладка 3: Аналитика
    # ══════════════════════════════════════════════════════════
    def _build_tab_analytics(self) -> tk.Frame:
        tab = tk.Frame(self.nb, bg=COLOR_BG)

        # Левая панель кнопок
        left = tk.Frame(tab, bg=COLOR_BG, width=220)
        left.pack(side="left", fill="y", padx=12, pady=12)
        left.pack_propagate(False)

        tk.Label(left, text="Режим 3: Аналитика",
                 bg=COLOR_BG, font=FONT_TITLE, fg=COLOR_ACCENT).pack(pady=(0, 10))

        make_btn(left, "📊 ABC-анализ",        self._show_abc).pack(pady=4)
        make_btn(left, "📉 XYZ-анализ",        self._show_xyz).pack(pady=4)
        make_btn(left, "🔲 ABC-XYZ матрица",   self._show_abcxyz).pack(pady=4)

        tk.Label(left, text="Динамика выручки:", bg=COLOR_BG, font=FONT_MAIN).pack(pady=(12, 2), anchor="w")
        tk.Label(left, text="Категория:", bg=COLOR_BG, font=FONT_MAIN).pack(anchor="w")

        self._cat_var = tk.StringVar(value="Все")
        self._cat_combo = ttk.Combobox(left, textvariable=self._cat_var, state="readonly", width=22)
        self._cat_combo["values"] = ["Все"]
        self._cat_combo.pack(pady=2)

        make_btn(left, "📈 Показать динамику", self._show_revenue_chart).pack(pady=4)
        make_btn(left, "🔄 Обновить категории", self._refresh_categories).pack(pady=4)

        # Правая область (вкладки для таблицы и графика)
        right = tk.Frame(tab, bg=COLOR_BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=12)

        self.ana_nb = ttk.Notebook(right)
        self.ana_nb.pack(fill="both", expand=True)

        self._ana_table_frame = tk.Frame(self.ana_nb, bg=COLOR_BG)
        self._ana_chart_frame = tk.Frame(self.ana_nb, bg=COLOR_BG)
        self.ana_nb.add(self._ana_table_frame, text="  Таблица  ")
        self.ana_nb.add(self._ana_chart_frame, text="  График  ")

        self._ana_tree = TreeviewFrame(self._ana_table_frame, columns=[])
        self._ana_tree.pack(fill="both", expand=True)

        self._ana_canvas_holder = tk.Frame(self._ana_chart_frame, bg=COLOR_BG)
        self._ana_canvas_holder.pack(fill="both", expand=True)

        return tab

    def _refresh_categories(self):
        try:
            cats = self.engine.get_categories()
            self._cat_combo["values"] = ["Все"] + cats
            self._set_status("Категории обновлены.")
        except Exception as e:
            self._set_status(f"Ошибка: {e}")

    def _show_abc(self):
        try:
            df = self.engine.abc_analysis()
            self._ana_tree.load(df)
            self.ana_nb.select(0)
            self._set_status("ABC-анализ выполнен.")
            # Диаграмма
            self._plot_abc(df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _plot_abc(self, df: pd.DataFrame):
        for w in self._ana_canvas_holder.winfo_children():
            w.destroy()
        fig, ax = plt.subplots(figsize=(7, 4), tight_layout=True)
        colors = {"A": "#2ECC71", "B": "#F39C12", "C": "#E74C3C"}
        bar_colors = [colors.get(g, "#999") for g in df["ABC"]]
        ax.bar(df["product_name"], df["revenue"], color=bar_colors)
        ax.set_title("ABC-анализ: выручка по товарам", fontsize=11)
        ax.set_ylabel("Выручка, руб.")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        # Легенда
        from matplotlib.patches import Patch
        legend = [Patch(color=c, label=f"Группа {k}") for k, c in colors.items()]
        ax.legend(handles=legend, fontsize=9)
        canvas = FigureCanvasTkAgg(fig, master=self._ana_canvas_holder)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.ana_nb.select(1)
        plt.close(fig)

    def _show_xyz(self):
        try:
            df = self.engine.xyz_analysis()
            self._ana_tree.load(df)
            self.ana_nb.select(0)
            self._set_status("XYZ-анализ выполнен.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _show_abcxyz(self):
        try:
            df = self.engine.abcxyz_matrix()
            self._ana_tree.load(df)
            self.ana_nb.select(0)
            self._set_status("ABC-XYZ матрица построена.")
            self._plot_abcxyz(df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _plot_abcxyz(self, df: pd.DataFrame):
        for w in self._ana_canvas_holder.winfo_children():
            w.destroy()

        # Тепловая карта
        pivot_data = {}
        for _, row in df.iterrows():
            a, x = row["ABC"], row["XYZ"]
            key = (a, x)
            pivot_data[key] = pivot_data.get(key, 0) + 1

        abc_groups = ["A", "B", "C"]
        xyz_groups = ["X", "Y", "Z"]
        matrix = pd.DataFrame(
            [[pivot_data.get((a, x), 0) for x in xyz_groups] for a in abc_groups],
            index=abc_groups, columns=xyz_groups,
        )

        fig, ax = plt.subplots(figsize=(5, 4), tight_layout=True)
        sns.heatmap(
            matrix, annot=True, fmt="d", cmap="YlGn",
            linewidths=0.5, ax=ax, cbar_kws={"label": "Кол-во товаров"},
        )
        ax.set_title("ABC-XYZ матрица (кол-во товаров)", fontsize=11)
        ax.set_xlabel("XYZ-группа")
        ax.set_ylabel("ABC-группа")
        canvas = FigureCanvasTkAgg(fig, master=self._ana_canvas_holder)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.ana_nb.select(1)
        plt.close(fig)

    def _show_revenue_chart(self):
        try:
            cat = self._cat_var.get()
            cat_param = None if cat == "Все" else cat
            df = self.engine.revenue_by_month(cat_param)

            for w in self._ana_canvas_holder.winfo_children():
                w.destroy()

            fig, ax = plt.subplots(figsize=(7, 4), tight_layout=True)
            ax.plot(df["period"], df["revenue"], marker="o", linewidth=2,
                    color="#4A90D9", markersize=5)
            ax.fill_between(df["period"], df["revenue"], alpha=0.15, color="#4A90D9")
            title = f"Динамика выручки: {cat}" if cat_param else "Динамика выручки (все категории)"
            ax.set_title(title, fontsize=11)
            ax.set_ylabel("Выручка, руб.")
            ax.set_xlabel("Период (год-месяц)")
            ax.tick_params(axis="x", rotation=45, labelsize=7)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.grid(axis="y", linestyle="--", alpha=0.5)

            canvas = FigureCanvasTkAgg(fig, master=self._ana_canvas_holder)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            self.ana_nb.select(1)
            plt.close(fig)

            self._ana_tree.load(df)
            self._set_status(f"Динамика выручки: {len(df)} периодов.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ══════════════════════════════════════════════════════════
    # Вкладка 4: Отчёты
    # ══════════════════════════════════════════════════════════
    def _build_tab_reports(self) -> tk.Frame:
        tab = tk.Frame(self.nb, bg=COLOR_BG)

        left = tk.Frame(tab, bg=COLOR_BG, width=220)
        left.pack(side="left", fill="y", padx=12, pady=12)
        left.pack_propagate(False)

        tk.Label(left, text="Режим 4: Отчёты",
                 bg=COLOR_BG, font=FONT_TITLE, fg=COLOR_ACCENT).pack(pady=(0, 10))

        reports = [
            ("📅 Выручка (посл. квартал)", self._report_quarter),
            ("🏆 Топ-10 товаров",          self._report_top10),
            ("🏪 Топ-5 магазинов",         self._report_top5),
            ("🚚 Отчёт по поставщикам",    self._report_suppliers),
        ]
        for label, cmd in reports:
            make_btn(left, label, cmd).pack(pady=4)

        right = tk.Frame(tab, bg=COLOR_BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=12)

        self._rep_title = tk.Label(right, text="Выберите отчёт слева",
                                   bg=COLOR_BG, font=FONT_TITLE, fg=COLOR_ACCENT)
        self._rep_title.pack(pady=(0, 6))

        self._rep_tree = TreeviewFrame(right, columns=[])
        self._rep_tree.pack(fill="both", expand=True)

        return tab

    def _load_report(self, title: str, df: pd.DataFrame):
        self._rep_title.config(text=title)
        self._rep_tree.load(df)
        self._set_status(f"{title}: {len(df)} строк.")

    def _report_quarter(self):
        try:
            df = self.reports.revenue_last_quarter()
            lbl = self.reports.last_quarter_label()
            self._load_report(f"Выручка за последний квартал ({lbl}) по городам", df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _report_top10(self):
        try:
            df = self.reports.top10_products()
            self._load_report("Топ-10 товаров по выручке", df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _report_top5(self):
        try:
            df = self.reports.top5_stores_avg_check()
            self._load_report("Топ-5 магазинов по среднему чеку", df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _report_suppliers(self):
        try:
            df = self.reports.supplier_report()
            self._load_report("Отчёт по поставщикам", df)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ══════════════════════════════════════════════════════════
    # Вкладка 5: Справка
    # ══════════════════════════════════════════════════════════
    def _build_tab_help(self) -> tk.Frame:
        tab = tk.Frame(self.nb, bg=COLOR_BG)
        txt = scrolledtext.ScrolledText(tab, font=("Consolas", 10), wrap="word",
                                        state="disabled", bg="#FAFBFF")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        content = self._get_help_text()
        txt.config(state="normal")
        txt.insert("1.0", content)
        txt.config(state="disabled")

        return tab

    def _get_help_text(self) -> str:
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║          ИАС РОЗНИЧНЫХ ПРОДАЖ — СПРАВОЧНАЯ ИНФОРМАЦИЯ            ║
╚══════════════════════════════════════════════════════════════════╝

О ПРОГРАММЕ
───────────
  Автор:    {self.AUTHOR}
  Группа:   {self.GROUP}
  Дата:     {self.APP_DATE}
  Версия:   {self.APP_VERSION}

  Программа предназначена для анализа данных розничных продаж
  в сети магазинов. Реализована в виде информационно-аналитической
  системы (ИАС) с компонентами ETL, хранилищем данных (SQLite),
  витриной данных и аналитическим движком.

РЕАЛИЗОВАННЫЕ ФУНКЦИИ
─────────────────────
  ✓ ETL-процесс: извлечение, преобразование, загрузка CSV → SQLite
  ✓ Проверка ссылочной целостности, удаление «грязных» данных
  ✓ Вычисление revenue = quantity × price; year, month, quarter
  ✓ Витрина данных (sales_mart) с агрегацией по времени/товару/магазину
  ✓ ABC-анализ товаров по выручке (группы A/B/C)
  ✓ XYZ-анализ товаров по коэффициенту вариации (группы X/Y/Z)
  ✓ Совмещённая матрица ABC-XYZ (тепловая карта)
  ✓ График динамики выручки по месяцам (с фильтром по категории)
  ✓ 4 стандартных отчёта: квартал/топ-товары/топ-магазины/поставщики
  ✓ Транзакционная загрузка данных (откат при ошибке)
  ✓ Проверка целостности БД + контрольная сумма

РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ
─────────────────────────
  Шаг 1. Файл → «Генерировать тестовые данные»
         Создаются CSV-файлы: sales.csv, products.csv, stores.csv
         в папке data/ (1500 продаж, 15 товаров, 8 магазинов).

  Шаг 2. Вкладка «ETL» → кнопка «Запустить ETL»
         Данные загружаются в SQLite (retail.db).
         В логе отображается статистика обработки.

  Шаг 3. Вкладка «Витрина» → «Построить витрину»
         Создаётся агрегированная таблица sales_mart.

  Шаг 4. Вкладка «Аналитика»:
         • ABC-анализ    — нажать «ABC-анализ»
         • XYZ-анализ    — нажать «XYZ-анализ»
         • Матрица       — нажать «ABC-XYZ матрица»
         • Динамика      — выбрать категорию, нажать «Показать динамику»

  Шаг 5. Вкладка «Отчёты» — выбрать нужный отчёт.

СТРУКТУРА ДАННЫХ
────────────────
  Таблицы SQLite:
    fact_sales   — факты продаж (sale_id, date, year, month,
                   quarter, product_id, store_id, quantity, price, revenue)
    dim_product  — товары (product_id, product_name, category, supplier)
    dim_store    — магазины (store_id, city, district, store_type)
    sales_mart   — витрина: агрегация по всем измерениям

ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ
───────────────────────
  Python ≥ 3.9
  Зависимости: pandas, numpy, matplotlib, seaborn, tkinter (встроен)

  Установка зависимостей:
    pip install pandas numpy matplotlib seaborn

"""

    # ── Диалоги меню Справка ─────────────────────────────────
    def _about(self):
        messagebox.showinfo(
            "О программе",
            f"ИАС Розничных продаж\n"
            f"Версия: {self.APP_VERSION}\n\n"
            f"Автор: {self.AUTHOR}\n"
            f"Группа: {self.GROUP}\n"
            f"Дата: {self.APP_DATE}\n\n"
            f"Информационно-аналитическая система для\n"
            f"анализа розничных продаж в сети магазинов.\n"
            f"Реализованы: ETL, витрина данных,\n"
            f"ABC/XYZ-анализ, отчёты.",
        )

    def _user_guide(self):
        self._switch_tab(4)


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = RetailIASApp()
    app.mainloop()
