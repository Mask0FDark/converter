#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Конвертер валют (сложный вариант):
- GUI: tkinter (вкладки Конвертер / История / График)
- Курсы: Exchangerate-API (актуальные), CoinGecko (крипто), Frankfurter (исторические фиатные ряды)
- История: JSON (поиск, экспорт CSV)
- Графики: matplotlib + pandas (фиат↔фиат через Frankfurter, крипто — через CoinGecko)
- Email: реальная отправка через SMTP (SSL)

Установка зависимостей:
  pip install requests pandas matplotlib

Запуск:
  python converter_app.py
"""

# =========================
# НАСТРАИВАЕМЫЕ ПЕРЕМЕННЫЕ
# =========================

# --- Exchangerate-API (актуальные фиат-курсы) ---
API_KEY = "cb06b1900cad4a93da3cad98"
EXR_API_BASE = "https://v6.exchangerate-api.com/v6"
FIAT_BASE_CURRENCY = "USD"

# --- Frankfurter (исторические ряды фиат) ---
FRANKFURTER_BASE = "https://api.frankfurter.app"
# Frankfurter возвращает только рабочие дни. Для стабильности берём end_date = вчера.

# --- CoinGecko (криптовалюты) ---
USE_CRYPTO = True
COINGECKO_SIMPLE_PRICE = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKET_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"
CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "SOL": "solana",
    "LTC": "litecoin",
    "ADA": "cardano",
    "TON": "toncoin",
    "DOT": "polkadot",
    "TRX": "tron",
}
CRYPTO_SIMPLE_VS = "usd"

# --- Поддержка валют в UI ---
SUPPORTED_FIAT = [
    "USD", "EUR", "RUB", "GBP", "JPY",
    "AUD", "CAD", "CHF", "CNY", "SEK", "NOK", "PLN", "CZK",
    "TRY", "INR", "BRL", "HKD", "SGD", "ZAR", "HUF", "MXN", "ILS", "DKK", "RON", "AED"
]
SUPPORTED_CRYPTO = list(CRYPTO_IDS.keys()) if USE_CRYPTO else []
SUPPORTED_ALL = SUPPORTED_FIAT + SUPPORTED_CRYPTO

# --- Настройки сети и автообновления ---
HTTP_TIMEOUT = 12  # сек
AUTO_REFRESH_ENABLED_BY_DEFAULT = True
REFRESH_INTERVAL_MS = 10 * 60 * 1000  # 10 минут
NOTIFY_THRESHOLD_PCT = 2.0  # уведомления по изменению фиат-курсов к USD

# --- История (JSON) ---
HISTORY_JSON_PATH = "history.json"
HISTORY_EXPORT_CSV_PATH = "history_export.csv"

# --- Кэш курсов ---
CACHE_RATES_FILE = "rates_cache.json"

# --- SMTP email (реальная отправка) ---
SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT = 465  # SSL
SMTP_LOGIN = "masaka200999@mail.ru"
SMTP_PASSWORD = "eD5pq3kdiYETWSGL6O34"  
EMAIL_DEFAULT_SUBJECT = "Результат конвертации валют"
EMAIL_OUTBOX_LOG_DIR = "sent_emails_logs"

# --- UI ---
APP_TITLE = "Конвертер валют • Сложный вариант"
WINDOW_SIZE = "1100x780"

# --- Графики ---
CHART_DEFAULT_FROM = "USD"
CHART_DEFAULT_TO = "EUR"
CHART_DEFAULT_DAYS = 7
CHART_ALLOWED_DAYS = [7, 30, 90]

# =========================
# ИМПОРТЫ
# =========================

import os
import csv
import ssl
import re
import json
import math
import smtplib
import traceback
from email.message import EmailMessage
from datetime import datetime, timedelta

import requests
import pandas as pd

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# =========================
# УТИЛИТЫ
# =========================

def ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def valid_email(addr: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr.strip()))


def pct_change(old: float, new: float) -> float:
    try:
        return (new - old) / old * 100.0
    except Exception:
        return float("inf")


def fmt_float(x, digits=6):
    try:
        return f"{float(x):,.{digits}f}".replace(",", " ")
    except Exception:
        return str(x)


# =========================
# СЕТЕВЫЕ ЗАПРОСЫ: КУРСЫ
# =========================

def fetch_fiat_rates_latest():
    """
    Актуальные фиат-курсы к USD через Exchangerate-API.
    Возвращает dict: {"USD":1.0,"EUR":0.9,...}
    """
    url = f"{EXR_API_BASE}/{API_KEY}/latest/{FIAT_BASE_CURRENCY}"
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()
    if js.get("result") != "success":
        raise RuntimeError(f"Exchangerate-API error: {js}")
    return js.get("conversion_rates", {})


def fetch_crypto_simple_prices(symbols, vs=CRYPTO_SIMPLE_VS):
    """
    Цены криптовалют в указанной фиат-валюте (по умолчанию USD) через CoinGecko.
    Возвращает dict: {'BTC': price_vs, ...}
    """
    if not symbols:
        return {}
    ids = ",".join(CRYPTO_IDS[s] for s in symbols if s in CRYPTO_IDS)
    if not ids:
        return {}
    params = {"ids": ids, "vs_currencies": vs}
    r = requests.get(COINGECKO_SIMPLE_PRICE, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()
    out = {}
    for sym, cid in CRYPTO_IDS.items():
        if sym in symbols:
            val = js.get(cid, {}).get(vs)
            if val is not None:
                out[sym] = float(val)
    return out


# =========================
# СЕТЕВЫЕ ЗАПРОСЫ: ИСТОРИЯ ДЛЯ ГРАФИКОВ
# =========================

def frankfurter_timeseries_direct(base_code: str, to_code: str, start_date, end_date) -> pd.Series:
    """
    Прямой запрос Frankfurter: /YYYY-MM-DD..YYYY-MM-DD?from=BASE&to=TO
    Возвращает Series(date->rate).
    """
    # Frankfurter: конец периода берём вчера (нет данных на сегодняшний ещё)
    end_date = (end_date - timedelta(days=1))
    url = f"{FRANKFURTER_BASE}/{start_date:%Y-%m-%d}..{end_date:%Y-%m-%d}"
    params = {"from": base_code, "to": to_code}
    r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()
    rates = js.get("rates", {})
    if not rates:
        return pd.Series(dtype=float)
    data = {d: v.get(to_code) for d, v in rates.items() if isinstance(v, dict)}
    s = pd.Series(data, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().dropna()
    return s


def frankfurter_timeseries_via_usd(base_code: str, to_code: str, start_date, end_date) -> pd.Series:
    """
    Фолбэк: через USD.
    Запрашиваем /timeseries с from=USD&to=base,to и считаем (USD->to)/(USD->base).
    """
    end_date = (end_date - timedelta(days=1))
    url = f"{FRANKFURTER_BASE}/{start_date:%Y-%m-%d}..{end_date:%Y-%m-%d}"
    params = {"from": "USD", "to": f"{base_code},{to_code}"}
    r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()
    rates = js.get("rates", {})
    if not rates:
        return pd.Series(dtype=float)

    rows = []
    for d, vals in rates.items():
        ub = vals.get(base_code)
        ut = vals.get(to_code)
        if ub and ut:
            rows.append((d, ut / ub))
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in rows}, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().dropna()
    return s


def fetch_timeseries_fiat(base_code: str, to_code: str, start_date, end_date) -> pd.Series:
    """
    Получает устойчивый временной ряд курса base->to:
    1) Пытается прямой запрос Frankfurter.
    2) Если нет — считает через USD.
    """
    if base_code == to_code:
        end_date = (end_date - timedelta(days=1))
        s = pd.Series(1.0, index=pd.date_range(start=start_date, end=end_date, freq="B"))
        return s

    try:
        s = frankfurter_timeseries_direct(base_code, to_code, start_date, end_date)
        if not s.empty:
            return s
    except Exception:
        pass

    s2 = frankfurter_timeseries_via_usd(base_code, to_code, start_date, end_date)
    if not s2.empty:
        return s2

    raise RuntimeError("Не удалось получить исторические данные (Frankfurter). Попробуйте другой период/пару.")


def fetch_crypto_market_chart_series(symbol: str, vs_currency: str, days: int) -> pd.Series:
    """
    Исторический ряд цены криптовалюты через CoinGecko market_chart.
    Возвращает Series(date->price) с дневной частотой.
    """
    cid = CRYPTO_IDS.get(symbol)
    if not cid:
        raise ValueError(f"Неизвестный тикер криптовалюты: {symbol}")
    url = COINGECKO_MARKET_CHART.format(id=cid)
    params = {"vs_currency": vs_currency.lower(), "days": int(days)}
    r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    js = r.json()
    prices = js.get("prices", [])
    if not prices:
        raise RuntimeError("Пустые данные market_chart")
    # Переводим в Series по датам (последнее наблюдение в дне)
    tmp = {}
    for t_ms, p in prices:
        d = datetime.utcfromtimestamp(int(t_ms) / 1000).date()
        tmp[d] = float(p)
    s = pd.Series(tmp, dtype=float)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return s


# =========================
# EMAIL
# =========================

def send_email_real(to_addr: str, subject: str, body: str):
    if not valid_email(to_addr):
        raise ValueError("Некорректный email получателя.")
    msg = EmailMessage()
    msg["From"] = SMTP_LOGIN
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_LOGIN, SMTP_PASSWORD)
        server.send_message(msg)

    # Логируем отправку (на всякий случай)
    ensure_dir(EMAIL_OUTBOX_LOG_DIR)
    fname = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path = os.path.join(EMAIL_OUTBOX_LOG_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"To: {to_addr}\nSubject: {subject}\n\n{body}\n")


# =========================
# ИСТОРИЯ (JSON)
# =========================

def load_history():
    return load_json(HISTORY_JSON_PATH, default=[])


def save_history(history_list):
    save_json(HISTORY_JSON_PATH, history_list)


def add_history_entry(entry):
    hist = load_history()
    hist.append(entry)
    save_history(hist)


def filter_history(query_text=None):
    rows = load_history()
    if not query_text:
        return rows
    q = str(query_text).strip().lower()
    def match(rec):
        return (
            q in rec.get("timestamp", "").lower()
            or q in str(rec.get("amount", "")).lower()
            or q in rec.get("from", "").lower()
            or q in rec.get("to", "").lower()
            or q in str(rec.get("rate", "")).lower()
            or q in str(rec.get("result", "")).lower()
        )
    return [r for r in rows if match(r)]


def export_history_csv(path: str):
    rows = load_history()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "amount", "from", "to", "rate", "result"])
        for r in rows:
            writer.writerow([
                r.get("timestamp"), r.get("amount"), r.get("from"),
                r.get("to"), r.get("rate"), r.get("result")
            ])


# =========================
# КОНВЕРТАЦИЯ
# =========================

def compute_cross_rate(from_code: str, to_code: str, fiat_rates_usd: dict, crypto_usd: dict) -> float:
    """
    Сколько to за 1 from:
      - Фиат↔Фиат: (USD->to) / (USD->from)
      - Крипта→Фиат: price_usd(from) * (USD->to)
      - Фиат→Крипта: 1 / ((USD->from) * price_usd(to))
      - Крипта↔Крипта: price_usd(from) / price_usd(to)
    """
    f, t = from_code.upper(), to_code.upper()
    if f == t:
        return 1.0

    def usd_to(code):
        return float(fiat_rates_usd.get(code, 0) or 0)

    def crypto_price_usd(sym):
        return float(crypto_usd.get(sym, 0) or 0)

    if f in SUPPORTED_FIAT and t in SUPPORTED_FIAT:
        a, b = usd_to(f), usd_to(t)
        if a > 0 and b > 0:
            return b / a
    elif f in SUPPORTED_CRYPTO and t in SUPPORTED_FIAT:
        p, b = crypto_price_usd(f), usd_to(t)
        if p > 0 and b > 0:
            return p * b
    elif f in SUPPORTED_FIAT and t in SUPPORTED_CRYPTO:
        a, p = usd_to(f), crypto_price_usd(t)
        if a > 0 and p > 0:
            return 1.0 / (a * p)
    elif f in SUPPORTED_CRYPTO and t in SUPPORTED_CRYPTO:
        pf, pt = crypto_price_usd(f), crypto_price_usd(t)
        if pf > 0 and pt > 0:
            return pf / pt

    raise ValueError("Недостаточно данных для вычисления курса. Обновите курсы и проверьте соединение.")


# =========================
# GUI
# =========================

class CurrencyConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)

        # Курсы
        self.fiat_rates = {}   # USD->code
        self.crypto_usd = {}   # symbol->price_usd

        # UI state
        self.auto_refresh_enabled = tk.BooleanVar(value=AUTO_REFRESH_ENABLED_BY_DEFAULT)

        self.amount_var = tk.StringVar(value="100")
        self.selected_from = tk.StringVar(value="USD")
        self.selected_to = tk.StringVar(value="EUR")
        self.result_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        # Email
        self.email_to_var = tk.StringVar(value="")
        self.email_subject_var = tk.StringVar(value=EMAIL_DEFAULT_SUBJECT)

        # История
        self.search_var = tk.StringVar(value="")

        # Графики
        self.chart_from = tk.StringVar(value=CHART_DEFAULT_FROM)
        self.chart_to = tk.StringVar(value=CHART_DEFAULT_TO)
        self.chart_period_days = tk.IntVar(value=CHART_DEFAULT_DAYS)
        self.chart_hint_var = tk.StringVar(value="")

        # Build UI
        self._build_ui()

        # Load cache and initial update
        self._load_cached_rates()
        self.after(200, self.update_rates)
        if self.auto_refresh_enabled.get():
            self._schedule_auto_refresh()

    # ----- UI -----

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_converter = ttk.Frame(notebook)
        self.tab_history = ttk.Frame(notebook)
        self.tab_chart = ttk.Frame(notebook)
        notebook.add(self.tab_converter, text="Конвертер")
        notebook.add(self.tab_history, text="История")
        notebook.add(self.tab_chart, text="График")

        self._build_converter_tab(self.tab_converter)
        self._build_history_tab(self.tab_history)
        self._build_chart_tab(self.tab_chart)

        status_bar = ttk.Frame(self)
        status_bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(status_bar, textvariable=self.status_var).pack(side="left")
        ttk.Checkbutton(status_bar, text="Автообновление каждые 10 минут",
                        variable=self.auto_refresh_enabled).pack(side="right")

    def _build_converter_tab(self, root):
        frm = ttk.Frame(root)
        frm.pack(fill="x", pady=10)

        ttk.Label(frm, text="Сумма:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(frm, textvariable=self.amount_var, width=18).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(frm, text="Из валюты:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        ttk.Combobox(frm, values=SUPPORTED_ALL, textvariable=self.selected_from, width=10, state="readonly").grid(row=0, column=3, padx=5, pady=5)

        ttk.Button(frm, text="↔", width=3, command=self._swap_currencies).grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(frm, text="В валюту:").grid(row=0, column=5, padx=5, pady=5, sticky="e")
        ttk.Combobox(frm, values=SUPPORTED_ALL, textvariable=self.selected_to, width=10, state="readonly").grid(row=0, column=6, padx=5, pady=5)

        ttk.Button(frm, text="Конвертировать", command=self.do_convert).grid(row=0, column=7, padx=5, pady=5)

        res_frm = ttk.LabelFrame(root, text="Результат")
        res_frm.pack(fill="x", padx=5, pady=10)
        ttk.Label(res_frm, textvariable=self.result_var, font=("Segoe UI", 14)).pack(anchor="w", padx=10, pady=12)

        mail_frm = ttk.LabelFrame(root, text="Отправить результат на email (SMTP)")
        mail_frm.pack(fill="x", padx=5, pady=10)
        ttk.Label(mail_frm, text="Email:").grid(row=0, column=0, padx=5, pady=6, sticky="e")
        ttk.Entry(mail_frm, textvariable=self.email_to_var, width=32).grid(row=0, column=1, padx=5, pady=6, sticky="w")
        ttk.Label(mail_frm, text="Тема:").grid(row=0, column=2, padx=5, pady=6, sticky="e")
        ttk.Entry(mail_frm, textvariable=self.email_subject_var, width=40).grid(row=0, column=3, padx=5, pady=6, sticky="w")
        ttk.Button(mail_frm, text="Отправить", command=self.on_send_email).grid(row=0, column=4, padx=8, pady=6)

        ttk.Label(root, text="Подсказка: если нет интернета — используются кэшированные курсы.").pack(anchor="w", padx=6, pady=(6, 0))

    def _build_history_tab(self, root):
        search_frm = ttk.Frame(root)
        search_frm.pack(fill="x", padx=5, pady=5)
        ttk.Label(search_frm, text="Поиск:").pack(side="left")
        ttk.Entry(search_frm, textvariable=self.search_var, width=32).pack(side="left", padx=5)
        ttk.Button(search_frm, text="Найти", command=self._reload_history_table).pack(side="left", padx=5)
        ttk.Button(search_frm, text="Сброс", command=self._reset_search).pack(side="left", padx=5)
        ttk.Button(search_frm, text="Экспорт CSV", command=self._export_csv_dialog).pack(side="right")

        columns = ("ts", "amount", "from", "to", "rate", "result")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=20)
        hdrs = [("ts", "Дата/время", 170), ("amount", "Сумма", 100), ("from", "Из", 80),
                ("to", "В", 80), ("rate", "Курс", 150), ("result", "Результат", 160)]
        for col, text, w in hdrs:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        self._reload_history_table()

    def _build_chart_tab(self, root):
        top = ttk.Frame(root)
        top.pack(fill="x", padx=5, pady=5)

        ttk.Label(top, text="Из:").pack(side="left")
        ttk.Combobox(top, values=SUPPORTED_ALL, textvariable=self.chart_from, width=10, state="readonly").pack(side="left", padx=4)

        ttk.Label(top, text="В:").pack(side="left", padx=(10, 0))
        ttk.Combobox(top, values=SUPPORTED_ALL, textvariable=self.chart_to, width=10, state="readonly").pack(side="left", padx=4)

        ttk.Label(top, text="Период:").pack(side="left", padx=(10, 0))
        for d in CHART_ALLOWED_DAYS:
            ttk.Radiobutton(top, text=f"{d} дн.", value=d, variable=self.chart_period_days, command=self._update_chart_hint).pack(side="left", padx=3)

        ttk.Button(top, text="Построить", command=self.draw_chart).pack(side="right")

        ttk.Label(root, textvariable=self.chart_hint_var).pack(anchor="w", padx=6)

        self.figure = Figure(figsize=(8.8, 4.6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=8)

        self._update_chart_hint()

    # ----- ЛОГИКА -----

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _swap_currencies(self):
        a, b = self.selected_from.get(), self.selected_to.get()
        self.selected_from.set(b)
        self.selected_to.set(a)

    def _load_cached_rates(self):
        data = load_json(CACHE_RATES_FILE, default={})
        self.fiat_rates = data.get("fiat_rates", {})
        self.crypto_usd = data.get("crypto_usd", {})
        if self.fiat_rates:
            self._set_status(f"Загружены кэшированные курсы ({len(self.fiat_rates)} фиат)")
        else:
            self._set_status("Кэш курсов пуст")

    def _save_cached_rates(self):
        save_json(CACHE_RATES_FILE, {
            "fiat_rates": self.fiat_rates,
            "crypto_usd": self.crypto_usd,
            "saved_at": datetime.now().isoformat(timespec="seconds")
        })

    def update_rates(self):
        try:
            new_fiat = fetch_fiat_rates_latest()
            new_crypto = fetch_crypto_simple_prices(SUPPORTED_CRYPTO, vs=CRYPTO_SIMPLE_VS) if USE_CRYPTO else {}
            self.fiat_rates, self.crypto_usd = new_fiat, new_crypto
            self._save_cached_rates()
            self._set_status(f"Курсы обновлены: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            self._set_status(f"Ошибка обновления: {e.__class__.__name__}. Использую кэш.")
        finally:
            self._update_chart_hint()

    def _schedule_auto_refresh(self):
        def periodic():
            if self.auto_refresh_enabled.get():
                self.update_rates()
            self.after(REFRESH_INTERVAL_MS, periodic)
        self.after(REFRESH_INTERVAL_MS, periodic)

    # ----- Конвертация и история -----

    def do_convert(self):
        try:
            amount_str = self.amount_var.get().strip().replace(",", ".")
            if not amount_str:
                raise ValueError("Введите сумму.")
            amount = float(amount_str)
            if not math.isfinite(amount):
                raise ValueError("Некорректная сумма.")

            from_code = self.selected_from.get().upper().strip()
            to_code = self.selected_to.get().upper().strip()
            if from_code not in SUPPORTED_ALL or to_code not in SUPPORTED_ALL:
                raise ValueError("Выбрана неподдерживаемая валюта.")

            rate = compute_cross_rate(from_code, to_code, self.fiat_rates, self.crypto_usd)
            result_value = amount * rate
            self.result_var.set(f"{fmt_float(result_value, 6)} {to_code}")

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_history_entry({
                "timestamp": ts,
                "amount": amount,
                "from": from_code,
                "to": to_code,
                "rate": rate,
                "result": result_value
            })
            self._reload_history_table()
        except Exception as e:
            messagebox.showerror("Ошибка конвертации", str(e))

    def on_send_email(self):
        try:
            to_addr = self.email_to_var.get().strip()
            subject = (self.email_subject_var.get().strip() or EMAIL_DEFAULT_SUBJECT)
            body = (
                f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Сумма: {self.amount_var.get()} {self.selected_from.get()}\n"
                f"Результат: {self.result_var.get()}\n"
            )
            send_email_real(to_addr, subject, body)
            messagebox.showinfo("Готово", "Письмо отправлено.")
        except Exception as e:
            messagebox.showerror("Ошибка отправки", str(e))

    # ----- История UI -----

    def _reload_history_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        query = self.search_var.get().strip() or None
        rows = filter_history(query)
        rows_sorted = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)
        for r in rows_sorted:
            self.tree.insert("", "end", values=(
                r.get("timestamp", ""),
                fmt_float(r.get("amount", 0), 6),
                r.get("from", ""),
                r.get("to", ""),
                fmt_float(r.get("rate", 0), 8),
                fmt_float(r.get("result", 0), 6),
            ))

    def _reset_search(self):
        self.search_var.set("")
        self._reload_history_table()

    def _export_csv_dialog(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить историю в CSV",
            defaultextension=".csv",
            initialfile=os.path.basename(HISTORY_EXPORT_CSV_PATH),
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        try:
            export_history_csv(path)
            messagebox.showinfo("Готово", f"Экспортировано: {path}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", str(e))

    # ----- Графики -----

    def _update_chart_hint(self):
        self.chart_hint_var.set(
            f"Пара: {self.chart_from.get()}→{self.chart_to.get()}. Период: {self.chart_period_days.get()} дней."
        )

    def draw_chart(self):
        from_code = self.chart_from.get().upper()
        to_code = self.chart_to.get().upper()
        days = int(self.chart_period_days.get())

        try:
            self.figure.clear()
            ax = self.figure.add_subplot(111)

            end = datetime.now().date()
            start = end - timedelta(days=days)

            # Фиат↔Фиат: Frankfurter
            if from_code in SUPPORTED_FIAT and to_code in SUPPORTED_FIAT:
                series = fetch_timeseries_fiat(from_code, to_code, start, end)
                ax.plot(series.index, series.values, color="#2563eb", linewidth=2)
                ax.set_ylabel(f"Курс ({from_code}→{to_code})")

            # Крипто→Фиат: CoinGecko
            elif from_code in SUPPORTED_CRYPTO and to_code in SUPPORTED_FIAT:
                series = fetch_crypto_market_chart_series(from_code, to_code, days)
                ax.plot(series.index, series.values, color="#059669", linewidth=2)
                ax.set_ylabel(f"Цена {from_code} в {to_code}")

            # Фиат→Крипто
            elif from_code in SUPPORTED_FIAT and to_code in SUPPORTED_CRYPTO:
                price = fetch_crypto_market_chart_series(to_code, from_code, days)  # цена крипты в фиате
                series = 1.0 / price
                ax.plot(series.index, series.values, color="#d97706", linewidth=2)
                ax.set_ylabel(f"{to_code} за 1 {from_code}")

            # Крипто↔Крипто
            elif from_code in SUPPORTED_CRYPTO and to_code in SUPPORTED_CRYPTO:
                s_from = fetch_crypto_market_chart_series(from_code, "usd", days)
                s_to = fetch_crypto_market_chart_series(to_code, "usd", days)
                df = pd.concat([s_from.rename("from"), s_to.rename("to")], axis=1).dropna()
                series = df["from"] / df["to"]
                ax.plot(series.index, series.values, color="#dc2626", linewidth=2)
                ax.set_ylabel(f"Курс ({from_code}→{to_code})")

            else:
                raise ValueError("Выбрана неподдерживаемая пара валют.")

            ax.set_title(f"{from_code} → {to_code} за последние {days} дней")
            ax.set_xlabel("Дата")
            ax.grid(True, alpha=0.3)
            self.canvas.draw()

            self.chart_hint_var.set(
                f"Точек: {len(series)}. Диапазон: {series.index.min().date()} — {series.index.max().date()}."
            )
        except requests.HTTPError as e:
            messagebox.showerror("Ошибка построения графика", f"HTTP ошибка: {e}")
        except Exception as e:
            messagebox.showerror("Ошибка построения графика", str(e))


# =========================
# ТОЧКА ВХОДА
# =========================

if __name__ == "__main__":
    app = CurrencyConverterApp()
    app.mainloop()
