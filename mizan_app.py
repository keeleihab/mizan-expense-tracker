"""
Mizan: Personal Expense Tracker (Streamlit edition)

Run with:
    streamlit run mizan_app.py

Uses the same expenses.csv and budget.csv files as the console version
(expense_tracker.py), so both always show the same data.
"""

import csv
import html
import io
import math
import os
import random
from calendar import monthrange
from datetime import date, datetime, timedelta

import altair as alt
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

# =============================================================================
# Configuration
# =============================================================================
EXPENSES_FILE = "expenses.csv"
BUDGET_FILE = "budget.csv"
FIELDS = ["description", "amount", "category", "date"]
DATE_FMT = "%Y-%m-%d"
MAX_AMOUNT = 1_000_000
MAX_DESC = 60

CATEGORIES = ["Food", "Transport", "Shopping", "Entertainment", "Other"]
CAT_EMOJI = {
    "Food": "🍲",
    "Transport": "🚕",
    "Shopping": "🛍️",
    "Entertainment": "🎬",
    "Other": "📦",
}
CAT_COLOR = {
    "Food": "#F2A93B",           # saffron
    "Transport": "#5B4BDB",      # majorelle blue
    "Shopping": "#E0607E",       # rose
    "Entertainment": "#2FA98C",  # mint tea
    "Other": "#A3927A",          # sand
}
MAJORELLE, SAFFRON, ROSE, MINT = "#5B4BDB", "#F2A93B", "#E0607E", "#2FA98C"

PAGES = ["🏠 Dashboard", "➕ Add expense", "📋 Expenses",
         "📊 Analytics", "💰 Budget", "🎲 Budget risk", "🗂️ Data"]

# Quick-add buttons on the Add page: (emoji, description, amount, category)
PRESETS = [
    ("☕", "Coffee", 15.0, "Food"),
    ("🚕", "Petit taxi", 20.0, "Transport"),
    ("🥙", "Lunch", 60.0, "Food"),
    ("🛒", "Groceries", 250.0, "Food"),
    ("🎬", "Cinema", 70.0, "Entertainment"),
    ("📱", "Phone top-up", 50.0, "Other"),
]

# Realistic expenses for the "Load sample data" button
SAMPLE_ITEMS = {
    "Food": [("Coffee at the café", 12, 22), ("Msemen and mint tea", 10, 20),
             ("Lunch tagine", 45, 95), ("Groceries at Marjane", 150, 450),
             ("Pizza delivery", 70, 140), ("Fruit and vegetables", 30, 90)],
    "Transport": [("Petit taxi", 10, 30), ("Grand taxi", 20, 60),
                  ("Careem ride", 25, 70), ("Fuel", 200, 400),
                  ("Train ticket", 60, 140)],
    "Shopping": [("Clothes", 180, 650), ("Books", 60, 240),
                 ("Pharmacy", 35, 160), ("Phone accessory", 90, 350)],
    "Entertainment": [("Cinema ticket", 50, 80), ("Football match", 50, 150),
                      ("Streaming subscription", 65, 65),
                      ("Bowling with friends", 60, 120), ("Concert", 120, 300)],
    "Other": [("Haircut", 40, 90), ("Gift for a friend", 100, 300),
              ("Laundry", 30, 60), ("Phone top-up", 20, 100)],
}
SAMPLE_WEIGHTS = {"Food": 0.42, "Transport": 0.25, "Shopping": 0.13,
                  "Entertainment": 0.12, "Other": 0.08}


# =============================================================================
# Validation and storage (csv module)
# =============================================================================
def clean_expense(description, amount, category, date_value, allow_future=False):
    """Validate one expense. Returns (expense_dict, None) or (None, error)."""
    description = "" if description is None else str(description).strip()
    if not description:
        return None, "Enter a description, for example Coffee or Taxi."
    if len(description) > MAX_DESC:
        return None, "Keep the description under %d characters." % MAX_DESC

    if amount is None or str(amount).strip() == "":
        return None, "Enter an amount in MAD."
    try:
        amount = round(float(str(amount).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None, "'%s' is not a number. Enter an amount like 25.50." % amount
    if math.isnan(amount) or amount <= 0:
        return None, "The amount must be greater than 0 MAD."
    if amount > MAX_AMOUNT:
        return None, "That amount looks too large. Check for an extra zero."

    if category not in CATEGORIES:
        return None, "Choose one of the categories: " + ", ".join(CATEGORIES) + "."

    if isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value.strip(), DATE_FMT).date()
        except ValueError:
            return None, "'%s' is not a valid date. Use YYYY-MM-DD." % date_value
    elif isinstance(date_value, datetime):  # also covers pandas Timestamps
        date_value = date_value.date()
    if not isinstance(date_value, date):
        return None, "Pick a date for the expense."
    if not allow_future and date_value > date.today():
        return None, "The date can't be in the future."

    return {"description": description, "amount": amount,
            "category": category, "date": date_value.strftime(DATE_FMT)}, None


def load_expenses():
    """Read all expenses from the CSV file. Corrupted rows are skipped."""
    expenses = []
    if not os.path.exists(EXPENSES_FILE):
        return expenses
    with open(EXPENSES_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            expense, _ = clean_expense(row.get("description"), row.get("amount"),
                                       row.get("category"), row.get("date") or "",
                                       allow_future=True)
            if expense:
                expenses.append(expense)
    return expenses


def save_expenses(expenses):
    with open(EXPENSES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(expenses)


def load_budget():
    if not os.path.exists(BUDGET_FILE):
        return None
    with open(BUDGET_FILE, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            try:
                value = float(row[0])
                return value if value > 0 else None
            except (IndexError, ValueError):
                return None
    return None


def save_budget(value):
    with open(BUDGET_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([value])


def csv_bytes(expenses):
    """Expenses as CSV bytes, for download buttons."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(expenses)
    return buffer.getvalue().encode("utf-8")


def parse_uploaded_csv(raw_bytes):
    """Read an uploaded CSV. Returns (valid expenses, number of skipped rows, error)."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], 0, "The file isn't UTF-8 text. Export it again as CSV (UTF-8)."
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [f for f in FIELDS if f not in headers]
    if missing:
        return [], 0, "The file is missing these columns: " + ", ".join(missing) + "."
    valid, skipped = [], 0
    for row in reader:
        row = {str(k).strip().lower(): v for k, v in row.items() if k}
        category = str(row.get("category") or "").strip().title()
        expense, _ = clean_expense(row.get("description"), row.get("amount"),
                                   category, row.get("date") or "")
        if expense:
            valid.append(expense)
        else:
            skipped += 1
    return valid, skipped, None


# =============================================================================
# Analysis helpers
# =============================================================================
def fmt(value):
    return "{:,.2f} MAD".format(value)


def cat_label(category):
    return "%s %s" % (CAT_EMOJI[category], category)


def calculate_total(expenses):
    return sum(e["amount"] for e in expenses)


def totals_by_category(expenses):
    totals = {c: 0.0 for c in CATEGORIES}
    for e in expenses:
        totals[e["category"]] += e["amount"]
    return totals


def to_frame(expenses):
    df = pd.DataFrame(expenses, columns=FIELDS)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    df["id"] = range(len(df))
    return df


def daily_average(df):
    if df.empty:
        return 0.0
    days = (date.today() - df["date"].min().date()).days + 1
    return df["amount"].sum() / max(days, 1)


def month_total(df, year, month):
    mask = (df["date"].dt.year == year) & (df["date"].dt.month == month)
    return float(df.loc[mask, "amount"].sum()), int(mask.sum())


# =============================================================================
# Monte Carlo budget risk
# =============================================================================
MC_SIMULATIONS = 10_000
MC_MIN_DAYS = 7
MC_HALF_LIFE = 21  # days; used when recent spending is weighted more


def daily_history(df):
    """Total spent on each calendar day from the first expense to today.
    Days with no spending are included as 0, because quiet days are part of the pattern."""
    past = df[df["date"].dt.date <= date.today()]
    if past.empty:
        return pd.Series(dtype=float)
    daily = past.groupby(past["date"].dt.normalize())["amount"].sum()
    days = pd.date_range(daily.index.min(), pd.Timestamp(date.today()))
    return daily.reindex(days, fill_value=0.0)


def simulate_spending(daily, horizon, weight_recent=False, n_sims=MC_SIMULATIONS, seed=42):
    """Bootstrap simulation of future spending.

    Each simulated future is built by drawing `horizon` days at random (with
    replacement) from the user's own daily spending history. Returns an array of
    shape (n_sims, horizon) with the cumulative extra spending along each path.
    """
    values = daily.to_numpy(dtype=float)
    probabilities = None
    if weight_recent:
        age = np.arange(len(values))[::-1]          # 0 = today, 1 = yesterday, ...
        weights = 0.5 ** (age / MC_HALF_LIFE)        # weight halves every MC_HALF_LIFE days
        probabilities = weights / weights.sum()
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(n_sims, horizon), replace=True, p=probabilities)
    return draws.cumsum(axis=1)


def pct_text(value):
    """Readable percentage: avoids showing a misleading 0% or 100% for rare outcomes."""
    if 0 < value < 1:
        return "less than 1%"
    if 99 < value < 100:
        return "more than 99%"
    return "%.0f%%" % value


def month_end_risk(df, budget):
    """Chance (0-100) of passing the budget by the end of this month, or None if
    there isn't enough history or no days are left to simulate."""
    daily = daily_history(df)
    today = date.today()
    days_left = monthrange(today.year, today.month)[1] - today.day
    if len(daily) < MC_MIN_DAYS or days_left < 1:
        return None
    total = df.loc[df["date"].dt.date <= today, "amount"].sum()
    paths = simulate_spending(daily, days_left)
    return float(((total + paths[:, -1]) > budget).mean() * 100)


def dark_mode():
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return True


CAT_SCALE = alt.Scale(domain=CATEGORIES, range=[CAT_COLOR[c] for c in CATEGORIES])


# =============================================================================
# Session helpers (messages that survive a rerun, page switching)
# =============================================================================
def notify(message, icon="✅"):
    st.session_state.setdefault("notices", []).append((message, icon))


def go_to(page):
    st.session_state["menu"] = page


def load_sample_data():
    rnd = random.Random()
    today = date.today()
    weights = [SAMPLE_WEIGHTS[c] for c in CATEGORIES]
    sample = []
    for _ in range(60):
        category = rnd.choices(CATEGORIES, weights=weights)[0]
        description, low, high = rnd.choice(SAMPLE_ITEMS[category])
        amount = rnd.uniform(low, high)
        amount = float(round(amount)) if high - low > 20 else round(amount, 2)
        day = today - timedelta(days=rnd.randint(0, 59))
        sample.append({"description": description, "amount": amount,
                       "category": category, "date": day.strftime(DATE_FMT)})
    expenses = load_expenses() + sample
    save_expenses(expenses)
    notify("Loaded 60 sample expenses.", "🎲")


def remove_budget():
    if os.path.exists(BUDGET_FILE):
        os.remove(BUDGET_FILE)
    notify("Budget removed.", "🗑️")


def undo_delete():
    restored = st.session_state.pop("undo", [])
    save_expenses(load_expenses() + restored)
    st.session_state["editor_v"] = st.session_state.get("editor_v", 0) + 1
    notify("Restored %d expense(s)." % len(restored), "↩️")


def apply_preset(description, amount, category):
    st.session_state["f_desc"] = description
    st.session_state["f_amount"] = amount
    st.session_state["f_cat"] = category


def submit_expense():
    """Runs when the Add expense form is submitted."""
    s = st.session_state
    expense, error = clean_expense(s["f_desc"], s["f_amount"], s["f_cat"], s["f_date"])
    if error:
        s["add_error"] = error
        return
    expenses = load_expenses()
    expenses.append(expense)
    save_expenses(expenses)
    s["last_added"] = expense
    s["f_desc"], s["f_amount"], s["f_date"] = "", None, date.today()
    notify("Added %s, %s." % (expense["description"], fmt(expense["amount"])))
    budget = load_budget()
    if budget and calculate_total(expenses) > budget:
        notify("You're now over your budget.", "⚠️")


# =============================================================================
# Styling
# =============================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=IBM+Plex+Mono:wght@400;600&display=swap');

h1, h2, h3, h4 { font-family: 'Bricolage Grotesque', 'Segoe UI', sans-serif !important; letter-spacing: -0.02em; }
h2 { font-weight: 800 !important; }
[data-testid="stMetricValue"] { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; letter-spacing: -0.02em; }

.mz-brand { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: 2.1rem; line-height: 1; letter-spacing: -0.04em; }
.mz-brand-sub { opacity: .65; font-size: .9rem; margin: .3rem 0 .4rem; }

.mz-hello { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: clamp(2.2rem, 4.4vw, 3.4rem); line-height: 1.02; letter-spacing: -0.04em; margin: .4rem 0 .7rem; }
.mz-lede { font-size: 1.08rem; line-height: 1.5; opacity: .82; max-width: 36rem; margin-bottom: 1.2rem; }

/* The receipt: the one bold element */
.mz-slot { max-width: 400px; margin: .6rem 0 0 auto; height: 10px; border-radius: 10px; background: rgba(128,128,150,.35); }
.mz-receipt-wrap { max-width: 400px; margin: -5px 0 0 auto; padding: 0 12px 18px; overflow: hidden; }
.mz-receipt { position: relative; background: #FFFDF6; color: #25212F; font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace; font-size: .84rem; line-height: 1.55; padding: 1.3rem 1.3rem 1rem; box-shadow: 0 22px 34px -22px rgba(30, 20, 80, .65); animation: mz-print 1.2s cubic-bezier(.25,.9,.3,1) both; }
.mz-receipt::after { content: ""; position: absolute; left: 0; right: 0; bottom: -11px; height: 12px;
  background: linear-gradient(135deg, #FFFDF6 50%, transparent 50%) 0 0 / 14px 12px repeat-x,
              linear-gradient(225deg, #FFFDF6 50%, transparent 50%) 0 0 / 14px 12px repeat-x; }
@keyframes mz-print { from { transform: translateY(-100%); } to { transform: translateY(0); } }
@media (prefers-reduced-motion: reduce) { .mz-receipt { animation: none; } }
.r-center { text-align: center; }
.r-title { font-weight: 600; font-size: 1.05rem; }
.r-muted { opacity: .6; font-size: .78rem; }
.r-rule { border-top: 1px dashed rgba(37,33,47,.45); margin: .7rem 0; }
.r-line { display: flex; align-items: baseline; gap: .4rem; }
.r-line .r-dots { flex: 1; border-bottom: 1px dotted rgba(37,33,47,.35); transform: translateY(-4px); }
.r-total { font-weight: 600; font-size: .98rem; }
.r-bad { color: #C2334F; font-weight: 600; }
.r-good { color: #1E8A6F; }
.r-barcode { height: 34px; margin: .8rem auto .2rem; width: 75%;
  background: repeating-linear-gradient(90deg, #25212F 0 2px, transparent 2px 4px, #25212F 4px 5px, transparent 5px 9px, #25212F 9px 12px, transparent 12px 14px); }

/* Budget gauge */
.mz-gauge { position: relative; width: 210px; height: 210px; margin: .4rem auto 1rem; }
.mz-ring { position: absolute; inset: 0; border-radius: 50%;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), rgba(128,128,150,.2) 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 20px), #000 calc(100% - 19px));
          mask: radial-gradient(farthest-side, transparent calc(100% - 20px), #000 calc(100% - 19px)); }
.mz-gauge-label { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.mz-gauge-pct { font-family: 'Bricolage Grotesque', sans-serif; font-size: 2.7rem; font-weight: 800; letter-spacing: -0.04em; line-height: 1; }
.mz-gauge-sub { opacity: .7; font-size: .85rem; margin: .2rem auto 0; max-width: 130px; line-height: 1.3; }

.mz-insight { font-size: 1rem; line-height: 1.5; padding: .55rem 0; border-bottom: 1px solid rgba(128,128,150,.18); }
.mz-insight:last-child { border-bottom: none; }
.mz-big-emoji { font-size: 2.6rem; line-height: 1; }
</style>
"""


def receipt_html(title, subtitle, lines, totals, footer):
    """Build the receipt card. lines: [(label, value)], totals: [(label, value, css)]."""
    def row(label, value, css=""):
        return ('<div class="r-line %s"><span>%s</span><span class="r-dots"></span>'
                '<span>%s</span></div>' % (css, html.escape(label), html.escape(value)))

    parts = ['<div class="mz-slot"></div><div class="mz-receipt-wrap"><div class="mz-receipt">',
             '<div class="r-center r-title">%s</div>' % html.escape(title),
             '<div class="r-center r-muted">%s</div>' % html.escape(subtitle),
             '<div class="r-rule"></div>']
    parts += [row(label, value) for label, value in lines]
    parts.append('<div class="r-rule"></div>')
    parts += [row(label, value, css) for label, value, css in totals]
    parts.append('<div class="r-rule"></div>')
    parts.append('<div class="r-center r-muted">%s</div>' % html.escape(footer))
    parts.append('<div class="r-barcode"></div></div></div>')
    return "".join(parts)


def gauge_html(percent, label="of budget used", thresholds=(80, 100)):
    low, high = thresholds
    color = MINT if percent < low else (SAFFRON if percent <= high else ROSE)
    return ('<div class="mz-gauge" style="--p:%.1f; --c:%s"><div class="mz-ring"></div>'
            '<div class="mz-gauge-label"><div class="mz-gauge-pct">%.0f%%</div>'
            '<div class="mz-gauge-sub">%s</div></div></div>'
            % (min(percent, 100), color, percent, html.escape(label)))


def category_bar_figure(totals, for_download=False):
    """Required Matplotlib chart: total spending by category."""
    light = for_download or not dark_mode()
    fg = "#25212F" if light else "#ECE9F5"
    grid = (0, 0, 0, .08) if light else (1, 1, 1, .07)
    cats = list(totals.keys())
    values = [totals[c] for c in cats]

    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    if for_download:
        fig.patch.set_facecolor("white")
    else:
        fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    bars = ax.bar(cats, values, color=[CAT_COLOR[c] for c in cats], width=0.62, zorder=3)
    ax.bar_label(bars, labels=["{:,.2f}".format(v) for v in values], padding=4,
                 color=fg, fontsize=9, fontweight="bold")
    ax.set_title("Total spending by category (MAD)", color=fg, fontsize=13,
                 fontweight="bold", loc="left", pad=14)
    ax.set_xlabel("Category", color=fg)
    ax.set_ylabel("Amount (MAD)", color=fg)
    ax.tick_params(colors=fg)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: "{:,.0f}".format(v)))
    ax.yaxis.grid(True, color=fg, alpha=0.12, linewidth=0.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(grid)
    ax.set_ylim(0, max(values) * 1.18 if max(values) > 0 else 1)
    fig.tight_layout()
    return fig


def figure_png(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()


# =============================================================================
# Dialogs
# =============================================================================
@st.dialog("Delete expenses?")
def confirm_delete(ids):
    expenses = load_expenses()
    items = [expenses[i] for i in ids if i < len(expenses)]
    st.write("%d expense(s) will be removed from your records:" % len(items))
    for e in items[:8]:
        st.markdown("- %s %s, **%s** on %s" % (CAT_EMOJI[e["category"]],
                                               e["description"], fmt(e["amount"]), e["date"]))
    if len(items) > 8:
        st.caption("and %d more" % (len(items) - 8))
    st.caption("You can undo this right after.")
    left, right = st.columns(2)
    if left.button("Delete", type="primary", width="stretch"):
        id_set = set(ids)
        save_expenses([e for i, e in enumerate(expenses) if i not in id_set])
        st.session_state["undo"] = items
        st.session_state["editor_v"] = st.session_state.get("editor_v", 0) + 1
        notify("Deleted %d expense(s)." % len(items), "🗑️")
        st.rerun()
    if right.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Delete all expenses?")
def confirm_clear():
    count = len(load_expenses())
    st.write("This removes all %d expenses. Download a backup first if you "
             "might want them later." % count)
    left, right = st.columns(2)
    if left.button("Delete everything", type="primary", width="stretch"):
        st.session_state["undo"] = load_expenses()
        save_expenses([])
        notify("All expenses deleted.", "🗑️")
        st.rerun()
    if right.button("Cancel", width="stretch"):
        st.rerun()


# =============================================================================
# Pages
# =============================================================================
def empty_state(message):
    st.info(message)
    left, right, _ = st.columns([1, 1, 3])
    left.button("Add an expense", type="primary", on_click=go_to, args=(PAGES[1],),
                width="stretch")
    right.button("Load sample data", on_click=load_sample_data, width="stretch")


def page_dashboard(expenses, budget):
    hour = datetime.now().hour
    greeting = "Good morning." if hour < 12 else ("Good afternoon." if hour < 18 else "Good evening.")

    if not expenses:
        st.markdown('<div class="mz-hello">Where did your dirhams go?</div>'
                    '<p class="mz-lede">Record your first expense and Mizan will show you, '
                    'or load sample data to explore every screen.</p>', unsafe_allow_html=True)
        empty_state("No expenses recorded yet.")
        return

    df = to_frame(expenses)
    total = df["amount"].sum()
    today = date.today()
    this_month, n_this_month = month_total(df, today.year, today.month)
    prev = today.replace(day=1) - timedelta(days=1)
    last_month, _ = month_total(df, prev.year, prev.month)
    avg = daily_average(df)
    biggest = max(expenses, key=lambda e: e["amount"])
    totals = totals_by_category(expenses)

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        lede = "You've spent %s this month across %d expense%s." % (
            fmt(this_month), n_this_month, "" if n_this_month == 1 else "s")
        if budget:
            used = total / budget * 100
            if total > budget:
                lede += " You're %s over your budget." % fmt(total - budget)
            else:
                lede += " %.0f%% of your budget is used, %s left." % (used, fmt(budget - total))
        st.markdown('<div class="mz-hello">%s</div><p class="mz-lede">%s</p>'
                    % (greeting, html.escape(lede)), unsafe_allow_html=True)

        m1, m2 = st.columns(2)
        m1.metric("Total spent", fmt(total), border=True)
        if last_month > 0:
            m2.metric("This month", fmt(this_month), border=True,
                      delta="{:+,.2f} MAD vs last month".format(this_month - last_month),
                      delta_color="inverse")
        else:
            m2.metric("This month", fmt(this_month), border=True)
        m3, m4 = st.columns(2)
        m3.metric("Daily average", fmt(avg), border=True,
                  help="Total spending divided by the days since your first expense.")
        m4.metric("Largest expense", fmt(biggest["amount"]), border=True,
                  help="%s on %s" % (biggest["description"], biggest["date"]))

    with right:
        lines = [(cat_label(c), "{:,.2f}".format(v))
                 for c, v in sorted(totals.items(), key=lambda x: -x[1]) if v > 0]
        sums = [("Total", fmt(total), "r-total")]
        if budget:
            sums.append(("Budget", "{:,.2f}".format(budget), ""))
            if total > budget:
                sums.append(("Over by", "{:,.2f}".format(total - budget), "r-bad"))
            else:
                sums.append(("Left", "{:,.2f}".format(budget - total), "r-good"))
        first = df["date"].min().strftime("%d %b")
        footer = "%d expenses, %s to %s" % (len(df), first, today.strftime("%d %b %Y"))
        st.markdown(receipt_html("Mizan", "Printed " + datetime.now().strftime("%d %b %Y, %H:%M"),
                                 lines, sums, footer), unsafe_allow_html=True)

    # --- Spending over time -------------------------------------------------
    head, toggle = st.columns([3, 1.3], vertical_alignment="bottom")
    head.subheader("Spending over time")
    view = toggle.segmented_control("View", ["Daily", "Cumulative"], default="Daily",
                                    label_visibility="collapsed") or "Daily"
    if view == "Daily":
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
            x=alt.X("yearmonthdate(date):T", title=None),
            y=alt.Y("sum(amount):Q", title="MAD per day"),
            color=alt.Color("category:N", scale=CAT_SCALE, title=None,
                            legend=alt.Legend(orient="bottom")),
            tooltip=[alt.Tooltip("yearmonthdate(date):T", title="Date"),
                     alt.Tooltip("category:N", title="Category"),
                     alt.Tooltip("sum(amount):Q", title="MAD", format=",.2f")],
        )
    else:
        daily = df.groupby(df["date"].dt.normalize())["amount"].sum()
        full_range = pd.date_range(daily.index.min(), pd.Timestamp(today))
        daily = daily.reindex(full_range, fill_value=0).cumsum().rename("cumulative")
        daily = daily.rename_axis("date").reset_index()
        chart = alt.Chart(daily).mark_area(
            line={"color": MAJORELLE, "strokeWidth": 2.5},
            color=alt.Gradient(gradient="linear", x1=1, x2=1, y1=1, y2=0,
                               stops=[alt.GradientStop(color="rgba(91,75,219,0.04)", offset=0),
                                      alt.GradientStop(color="rgba(91,75,219,0.45)", offset=1)]),
        ).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("cumulative:Q", title="Cumulative MAD"),
            tooltip=[alt.Tooltip("date:T", title="Date"),
                     alt.Tooltip("cumulative:Q", title="Spent so far", format=",.2f")],
        )
        if budget:
            rule_df = pd.DataFrame({"budget": [budget], "label": ["Budget " + fmt(budget)]})
            rule = alt.Chart(rule_df).mark_rule(color=ROSE, strokeDash=[6, 4], strokeWidth=2).encode(y="budget:Q")
            text = alt.Chart(rule_df).mark_text(color=ROSE, align="left", dx=6, dy=-8,
                                                fontWeight="bold").encode(
                y="budget:Q", text="label:N", x=alt.value(0))
            chart = alt.layer(chart, rule, text)
    st.altair_chart(chart.properties(height=290))

    # --- Insights and recent ------------------------------------------------
    ins_col, recent_col = st.columns([1.1, 1], gap="large")
    with ins_col:
        st.subheader("What stands out")
        st.markdown("".join('<div class="mz-insight">%s</div>' % html.escape(t)
                            for t in build_insights(df, budget)), unsafe_allow_html=True)
    with recent_col:
        st.subheader("Recent expenses")
        recent = df.sort_values(["date", "id"], ascending=False).head(6).copy()
        recent["category"] = recent["category"].map(cat_label)
        recent["date"] = recent["date"].dt.date
        st.dataframe(recent[["date", "description", "category", "amount"]], hide_index=True,
                     width="stretch", column_config={
                         "date": st.column_config.DateColumn("Date", format="DD MMM"),
                         "description": "Description",
                         "category": "Category",
                         "amount": st.column_config.NumberColumn("MAD", format="%.2f"),
                     })
        st.button("See all expenses", on_click=go_to, args=(PAGES[2],))


def build_insights(df, budget):
    total = df["amount"].sum()
    today = date.today()
    insights = []

    by_cat = df.groupby("category")["amount"].sum().sort_values(ascending=False)
    top = by_cat.index[0]
    insights.append("%s %s is your biggest category, %.0f%% of everything you've spent (%s)."
                    % (CAT_EMOJI[top], top, by_cat.iloc[0] / total * 100, fmt(by_cat.iloc[0])))

    weekday = df.groupby(df["date"].dt.day_name())["amount"].sum()
    insights.append("📅 You spend the most on %ss: %s in total so far."
                    % (weekday.idxmax(), fmt(weekday.max())))

    small = df[df["amount"] < 30]
    if len(small) >= 3:
        insights.append("🪙 Small purchases add up: %d expenses under 30 MAD total %s."
                        % (len(small), fmt(small["amount"].sum())))

    spent_month, _ = month_total(df, today.year, today.month)
    if spent_month > 0:
        days_in_month = monthrange(today.year, today.month)[1]
        projection = spent_month / today.day * days_in_month
        insights.append("📈 At this month's pace you'll spend about %s by the end of %s."
                        % (fmt(projection), today.strftime("%B")))

    if budget:
        avg = daily_average(df)
        if total > budget:
            insights.append("⚠️ You're %s over budget. Cutting your top category would help most."
                            % fmt(total - budget))
        elif avg > 0:
            runway = int((budget - total) / avg)
            end = today + timedelta(days=runway)
            insights.append("💰 At %s a day, your remaining budget lasts about %d more days, "
                            "until %s." % (fmt(avg), runway, end.strftime("%d %B")))
            risk = month_end_risk(df, budget)
            if risk is not None and risk > 0:
                insights.append("🎲 In 10,000 simulated futures, you go over budget by the end "
                                "of %s in %s of them." % (today.strftime("%B"), pct_text(risk)))
            elif risk is not None:
                insights.append("🎲 You stay within budget until the end of %s in all 10,000 "
                                "simulated futures." % today.strftime("%B"))
    return insights


def page_add(expenses, budget):
    st.markdown("## Add an expense")
    st.caption("Fill in the form, or tap a quick-add button to prefill it.")

    s = st.session_state
    s.setdefault("f_desc", "")
    s.setdefault("f_amount", None)
    s.setdefault("f_cat", "Food")
    s.setdefault("f_date", date.today())

    form_col, receipt_col = st.columns([1.3, 1], gap="large")
    with form_col:
        preset_cols = st.columns(3)
        for i, (emoji, desc, amount, cat) in enumerate(PRESETS):
            preset_cols[i % 3].button("%s %s" % (emoji, desc), key="preset_%d" % i,
                                      on_click=apply_preset, args=(desc, amount, cat),
                                      width="stretch")

        with st.form("add_form", border=True):
            st.text_input("Description", key="f_desc", max_chars=MAX_DESC,
                          placeholder="Coffee, Taxi, Lunch...")
            c1, c2 = st.columns(2)
            c1.number_input("Amount (MAD)", key="f_amount", min_value=0.0, step=5.0,
                            format="%.2f", placeholder="0.00")
            c2.date_input("Date", key="f_date", max_value=date.today(), format="DD/MM/YYYY")
            st.radio("Category", CATEGORIES, key="f_cat", format_func=cat_label, horizontal=True)
            st.form_submit_button("Add expense", type="primary", on_click=submit_expense,
                                  width="stretch")

        if "add_error" in s:
            st.error(s.pop("add_error"))

        if budget:
            total = calculate_total(expenses)
            if total > budget:
                st.error("You're %s over your budget." % fmt(total - budget))
            else:
                st.progress(total / budget,
                            text="%s of your %s budget left" % (fmt(budget - total), fmt(budget)))

    with receipt_col:
        today = date.today().strftime(DATE_FMT)
        todays = [e for e in expenses if e["date"] == today]
        if todays:
            lines = [("%s %s" % (CAT_EMOJI[e["category"]], e["description"][:22]),
                      "{:,.2f}".format(e["amount"])) for e in todays[-8:]]
            footer = "%d expense%s today" % (len(todays), "" if len(todays) == 1 else "s")
            st.markdown(receipt_html("Today so far", date.today().strftime("%A %d %B"), lines,
                                     [("Total", fmt(calculate_total(todays)), "r-total")], footer),
                        unsafe_allow_html=True)
        else:
            st.info("Nothing recorded today yet. Expenses you add for today will show up here.")


def page_expenses(expenses):
    st.markdown("## Expenses")
    st.caption("Search, filter, edit any cell, and tick rows to delete them.")

    if st.session_state.get("undo"):
        box = st.container(border=True)
        a, b = box.columns([4, 1])
        a.write("Deleted %d expense(s)." % len(st.session_state["undo"]))
        b.button("Undo", on_click=undo_delete, width="stretch")

    if not expenses:
        empty_state("No expenses to show yet.")
        return

    df = to_frame(expenses)
    st.session_state.setdefault("editor_v", 0)

    # --- Search and filter --------------------------------------------------
    f1, f2, f3 = st.columns([1.4, 2, 1.4])
    query = f1.text_input("Search descriptions", placeholder="e.g. taxi")
    labels = [cat_label(c) for c in CATEGORIES]
    picked_labels = f2.multiselect("Categories", labels, default=labels)
    cats = [c for c in CATEGORIES if cat_label(c) in picked_labels]
    min_d, max_d = df["date"].min().date(), df["date"].max().date()
    picked = f3.date_input("Dates", value=(min_d, max_d), min_value=min_d, max_value=max_d,
                           format="DD/MM/YYYY")
    start, end = (picked[0], picked[-1]) if isinstance(picked, (tuple, list)) and picked else (min_d, max_d)

    g1, g2 = st.columns([3, 1.4])
    top_amount = float(math.ceil(df["amount"].max()))
    low, high = g1.slider("Amount range (MAD)", 0.0, top_amount, (0.0, top_amount)) \
        if top_amount > 0 else (0.0, 0.0)
    order = g2.selectbox("Sort by", ["Newest first", "Oldest first",
                                     "Highest amount", "Lowest amount"])

    mask = (df["category"].isin(cats)
            & df["description"].str.lower().str.contains(query.strip().lower(), regex=False)
            & (df["date"].dt.date >= start) & (df["date"].dt.date <= end)
            & (df["amount"] >= low) & (df["amount"] <= high))
    view = df[mask]
    sort_map = {"Newest first": (["date", "id"], False), "Oldest first": (["date", "id"], True),
                "Highest amount": (["amount"], False), "Lowest amount": (["amount"], True)}
    by, asc = sort_map[order]
    view = view.sort_values(by, ascending=asc)

    st.markdown("**%d** of %d expenses match, totaling **%s**."
                % (len(view), len(df), fmt(view["amount"].sum())))
    if view.empty:
        st.info("Nothing matches these filters. Clear the search or widen the date range.")
        return

    # --- Editable table -----------------------------------------------------
    table = view[["id", "date", "description", "category", "amount"]].copy()
    table["date"] = table["date"].dt.date
    table.insert(0, "delete", False)
    table = table.set_index("id")
    key = "editor_%d_%d" % (st.session_state["editor_v"], abs(hash(tuple(table.index))))
    edited = st.data_editor(
        table, key=key, hide_index=True, width="stretch", num_rows="fixed",
        column_config={
            "delete": st.column_config.CheckboxColumn("🗑️", help="Tick to delete", width="small"),
            "date": st.column_config.DateColumn("Date", format="DD MMM YYYY",
                                                max_value=date.today(), required=True),
            "description": st.column_config.TextColumn("Description", max_chars=MAX_DESC,
                                                       required=True, width="large"),
            "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES,
                                                         required=True),
            "amount": st.column_config.NumberColumn("Amount (MAD)", min_value=0.01,
                                                    format="%.2f", required=True),
        },
    )

    changes, errors = {}, []
    for rid, row in edited.iterrows():
        cleaned, error = clean_expense(row["description"], row["amount"],
                                       row["category"], row["date"])
        original = expenses[rid]
        if error:
            errors.append("%s: %s" % (original["description"], error))
        elif cleaned != original:
            changes[rid] = cleaned
    selected = edited.index[edited["delete"].astype(bool)].tolist()

    for error in errors:
        st.error(error)

    b1, b2, b3 = st.columns(3)
    if b1.button("Save %d change%s" % (len(changes), "" if len(changes) == 1 else "s"),
                 type="primary", disabled=not changes or bool(errors), width="stretch"):
        for rid, cleaned in changes.items():
            expenses[rid] = cleaned
        save_expenses(expenses)
        st.session_state["editor_v"] += 1
        notify("Saved %d change(s)." % len(changes))
        st.rerun()
    if b2.button("Delete %d selected" % len(selected), disabled=not selected,
                 width="stretch"):
        confirm_delete(selected)
    b3.download_button("Download these as CSV", csv_bytes([expenses[i] for i in view["id"]]),
                       file_name="expenses_filtered.csv", mime="text/csv",
                       width="stretch")


def page_analytics(expenses):
    st.markdown("## Analytics")
    if not expenses:
        empty_state("Add a few expenses to see your spending patterns.")
        return

    df = to_frame(expenses)
    total = df["amount"].sum()
    totals = totals_by_category(expenses)
    counts = df["category"].value_counts()
    top = max(totals, key=totals.get)

    left, right = st.columns([1.1, 1.4], gap="large")
    with left:
        with st.container(border=True):
            a, b = st.columns([1, 4])
            a.markdown('<div class="mz-big-emoji">%s</div>' % CAT_EMOJI[top], unsafe_allow_html=True)
            b.markdown("**%s is your highest spending category**  \n%s, %.0f%% of the total"
                       % (top, fmt(totals[top]), totals[top] / total * 100))

        summary = pd.DataFrame({
            "Category": [cat_label(c) for c in CATEGORIES],
            "Total": [totals[c] for c in CATEGORIES],
            "Expenses": [int(counts.get(c, 0)) for c in CATEGORIES],
            "Share": [totals[c] / total * 100 for c in CATEGORIES],
        }).sort_values("Total", ascending=False)
        st.dataframe(summary, hide_index=True, width="stretch", column_config={
            "Total": st.column_config.NumberColumn("Total (MAD)", format="%.2f"),
            "Share": st.column_config.ProgressColumn("Share", format="%.0f%%",
                                                     min_value=0, max_value=100),
        })
        st.metric("All categories", fmt(total), border=True)

    with right:
        t1, t2, t3, t4 = st.tabs(["By category", "Share", "Monthly", "Weekdays"])
        with t1:
            st.pyplot(category_bar_figure(totals))
            st.download_button("Download chart (PNG)",
                               figure_png(category_bar_figure(totals, for_download=True)),
                               file_name="spending_by_category.png", mime="image/png")
        with t2:
            share_df = pd.DataFrame({"category": CATEGORIES,
                                     "amount": [totals[c] for c in CATEGORIES]})
            share_df = share_df[share_df["amount"] > 0]
            donut = alt.Chart(share_df).mark_arc(innerRadius=85, outerRadius=140,
                                                 cornerRadius=4, padAngle=0.015).encode(
                theta="amount:Q",
                color=alt.Color("category:N", scale=CAT_SCALE, title=None,
                                legend=alt.Legend(orient="right")),
                tooltip=[alt.Tooltip("category:N", title="Category"),
                         alt.Tooltip("amount:Q", title="MAD", format=",.2f")],
            )
            center = alt.Chart(pd.DataFrame({"t": [fmt(total)]})).mark_text(
                fontSize=17, fontWeight="bold", color="#ECE9F5" if dark_mode() else "#25212F"
            ).encode(text="t:N")
            st.altair_chart((donut + center).properties(height=330))
        with t3:
            monthly = alt.Chart(df).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("yearmonth(date):O", title=None),
                y=alt.Y("sum(amount):Q", title="MAD"),
                color=alt.Color("category:N", scale=CAT_SCALE, title=None,
                                legend=alt.Legend(orient="bottom")),
                tooltip=[alt.Tooltip("yearmonth(date):O", title="Month"),
                         alt.Tooltip("category:N", title="Category"),
                         alt.Tooltip("sum(amount):Q", title="MAD", format=",.2f")],
            ).properties(height=330)
            st.altair_chart(monthly)
        with t4:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            wd = df.assign(weekday=df["date"].dt.day_name())
            weekday_chart = alt.Chart(wd).mark_bar(color=MAJORELLE, cornerRadiusTopLeft=3,
                                                   cornerRadiusTopRight=3).encode(
                x=alt.X("weekday:N", sort=days, title=None),
                y=alt.Y("sum(amount):Q", title="MAD"),
                tooltip=[alt.Tooltip("weekday:N", title="Day"),
                         alt.Tooltip("sum(amount):Q", title="MAD", format=",.2f"),
                         alt.Tooltip("count():Q", title="Expenses")],
            ).properties(height=330)
            st.altair_chart(weekday_chart)


def page_budget(expenses, budget):
    st.markdown("## Budget")
    total = calculate_total(expenses)

    left, right = st.columns([1, 1.2], gap="large")
    with left:
        with st.form("budget_form", border=True):
            new_budget = st.number_input("Spending budget (MAD)", min_value=0.0, step=100.0,
                                         value=float(budget or 0.0), format="%.2f")
            saved = st.form_submit_button("Save budget", type="primary", width="stretch")
        if saved:
            if new_budget <= 0:
                st.error("Enter a budget greater than 0 MAD.")
            else:
                save_budget(round(new_budget, 2))
                notify("Budget saved: %s." % fmt(new_budget), "💰")
                st.rerun()
        if budget:
            st.button("See your budget risk", on_click=go_to, args=(PAGES[5],), type="primary")
            st.button("Remove budget", on_click=remove_budget)

    with right:
        if not budget:
            st.info("Set a budget to see how much you have left and how fast you're using it.")
            return
        percent = total / budget * 100
        st.markdown(gauge_html(percent), unsafe_allow_html=True)
        if percent > 100:
            st.error("⚠️ You've spent %s more than your budget." % fmt(total - budget))
        elif percent >= 80:
            st.warning("You've used %.0f%% of your budget. %s left." % (percent, fmt(budget - total)))
        else:
            st.success("You're on track, with %s left." % fmt(budget - total))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Budget", fmt(budget), border=True)
    m2.metric("Spent", fmt(total), border=True)
    if total > budget:
        m3.metric("Over budget by", fmt(total - budget), border=True)
    else:
        m3.metric("Remaining", fmt(budget - total), border=True)
    m4.metric("Budget used", "%.1f%%" % percent, border=True)

    if expenses:
        st.subheader("Where the budget went")
        totals = totals_by_category(expenses)
        used = pd.DataFrame({
            "Category": [cat_label(c) for c in CATEGORIES],
            "Spent": [totals[c] for c in CATEGORIES],
            "Of budget": [totals[c] / budget * 100 for c in CATEGORIES],
        }).sort_values("Spent", ascending=False)
        st.dataframe(used, hide_index=True, width="stretch", column_config={
            "Spent": st.column_config.NumberColumn("Spent (MAD)", format="%.2f"),
            "Of budget": st.column_config.ProgressColumn("Share of budget", format="%.1f%%",
                                                         min_value=0, max_value=100),
        })


def page_risk(expenses, budget):
    st.markdown("## Budget risk")
    st.caption("A Monte Carlo simulation of how your spending could play out, "
               "built from your own day-to-day history.")

    if not budget:
        st.info("Set a budget first. The simulation estimates your chance of going over it.")
        st.button("Set a budget", on_click=go_to, args=(PAGES[4],), type="primary")
        return
    if not expenses:
        empty_state("Add some expenses so the simulation has history to learn from.")
        return

    df = to_frame(expenses)
    daily = daily_history(df)
    if len(daily) < MC_MIN_DAYS:
        st.warning("The simulation needs at least %d days of history to learn from, and you "
                   "have %d so far. Keep logging, or load sample data to try it out."
                   % (MC_MIN_DAYS, len(daily)))
        st.button("Load sample data", on_click=load_sample_data)
        return

    today = date.today()
    days_left = monthrange(today.year, today.month)[1] - today.day
    total = float(df.loc[df["date"].dt.date <= today, "amount"].sum())
    st.session_state.setdefault("mc_seed", 42)

    # --- Controls -----------------------------------------------------------
    c1, c2, c3 = st.columns([2.2, 1.4, 1], vertical_alignment="bottom")
    horizon = c1.slider("Days to simulate", 1, 90, max(days_left, 1),
                        help="Starts at the days left in this month, not counting today.")
    weight_recent = c2.toggle("Weight recent weeks more", value=False,
                              help="A day's chance of being drawn halves every %d days back, "
                                   "so your latest habits count most." % MC_HALF_LIFE)
    if c3.button("Re-run", width="stretch",
                 help="Run the 10,000 simulations again with a new random seed."):
        st.session_state["mc_seed"] += 1

    paths = simulate_spending(daily, horizon, weight_recent, seed=st.session_state["mc_seed"])
    finals = total + paths[:, -1]
    risk = float((finals > budget).mean() * 100)
    p10, p50, p90 = np.percentile(finals, [10, 50, 90])
    end_date = today + timedelta(days=horizon)
    end_label = end_date.strftime("%d %B")
    remaining = budget - total

    # --- Headline -----------------------------------------------------------
    left, right = st.columns([1, 1.6], gap="large")
    with left:
        st.markdown(gauge_html(risk, "chance of going over budget",
                               thresholds=(25, 60)), unsafe_allow_html=True)
    with right:
        if remaining <= 0:
            st.error("You're already %s over budget, so the risk is 100%%. The simulation "
                     "shows how much further spending could go by %s." % (fmt(-remaining), end_label))
        elif risk >= 60:
            st.error("High risk: in %s of 10,000 simulated futures you pass your budget "
                     "by %s." % (pct_text(risk), end_label))
        elif risk >= 25:
            st.warning("Moderate risk: %s of simulated futures go over budget by %s."
                       % (pct_text(risk), end_label))
        elif risk > 0:
            st.success("Low risk: %s of simulated futures go over budget by %s."
                       % (pct_text(risk), end_label))
        else:
            st.success("Very low risk: none of the 10,000 simulated futures go over budget by %s."
                       % end_label)
        m1, m2 = st.columns(2)
        m1.metric("Likely total by " + end_label, fmt(p50), border=True,
                  help="The median outcome: half of the simulations end above this, half below.")
        m2.metric("80% range", "{:,.0f} to {:,.0f}".format(p10, p90), border=True,
                  help="8 out of 10 simulations end between these two totals (10th to 90th percentile).")
        m3, m4 = st.columns(2)
        if remaining > 0:
            m3.metric("Safe daily spend", fmt(remaining / horizon), border=True,
                      help="What you can spend per day for the next %d days and still finish "
                           "exactly on budget." % horizon)
        else:
            m3.metric("Safe daily spend", fmt(0), border=True)
        m4.metric("Your average day", fmt(float(daily.mean())), border=True,
                  help="Average over all %d days of history, including days with no spending."
                       % len(daily))

    # --- Charts -------------------------------------------------------------
    tab1, tab2 = st.tabs(["Possible outcomes", "Spending paths"])
    with tab1:
        counts, edges = np.histogram(finals, bins=40)
        hist = pd.DataFrame({"start": edges[:-1], "end": edges[1:], "count": counts})
        hist["share"] = hist["count"] / MC_SIMULATIONS * 100
        hist["outcome"] = np.where((hist["start"] + hist["end"]) / 2 > budget,
                                   "Over budget", "Within budget")
        bars = alt.Chart(hist).mark_bar().encode(
            x=alt.X("start:Q", title="Total spent by %s (MAD)" % end_label, bin="binned"),
            x2="end:Q",
            y=alt.Y("share:Q", title="% of simulations",
                    scale=alt.Scale(domain=[0, float(hist["share"].max()) * 1.3])),
            color=alt.Color("outcome:N", title=None, legend=alt.Legend(orient="bottom"),
                            scale=alt.Scale(domain=["Within budget", "Over budget"],
                                            range=[MINT, ROSE])),
            tooltip=[alt.Tooltip("start:Q", title="From (MAD)", format=",.0f"),
                     alt.Tooltip("end:Q", title="To (MAD)", format=",.0f"),
                     alt.Tooltip("share:Q", title="% of simulations", format=".1f")],
        )
        marks = pd.DataFrame({"x": [budget, p50], "ypos": [12, 30],
                              "label": ["Budget " + fmt(budget), "Median " + fmt(p50)]})
        ink = "#ECE9F5" if dark_mode() else "#25212F"
        rules = alt.Chart(marks).mark_rule(strokeDash=[6, 4], strokeWidth=2).encode(
            x="x:Q", color=alt.value(ink))
        labels = alt.Chart(marks).mark_text(align="left", dx=5, fontWeight="bold",
                                            color=ink).encode(
            x="x:Q", y=alt.Y("ypos:Q", scale=None, axis=None), text="label:N")
        st.altair_chart(alt.layer(bars, rules, labels).properties(height=340))
        st.caption("Each bar shows how many of the 10,000 simulated futures ended in that range.")

    with tab2:
        steps = np.arange(horizon + 1)
        cumulative = np.hstack([np.zeros((paths.shape[0], 1)), paths]) + total
        bands = pd.DataFrame({
            "date": [pd.Timestamp(today + timedelta(days=int(s))) for s in steps],
            "p5": np.percentile(cumulative, 5, axis=0),
            "p25": np.percentile(cumulative, 25, axis=0),
            "p50": np.percentile(cumulative, 50, axis=0),
            "p75": np.percentile(cumulative, 75, axis=0),
            "p95": np.percentile(cumulative, 95, axis=0),
        })
        sample = []
        for i in range(25):
            for s in steps:
                sample.append({"date": bands["date"].iloc[s], "path": i,
                               "total": float(cumulative[i, s])})
        sample = pd.DataFrame(sample)

        x = alt.X("date:T", title=None)
        outer = alt.Chart(bands).mark_area(opacity=0.18, color=MAJORELLE).encode(
            x=x, y=alt.Y("p5:Q", title="Total spent (MAD)", scale=alt.Scale(zero=False)),
            y2="p95:Q")
        inner = alt.Chart(bands).mark_area(opacity=0.32, color=MAJORELLE).encode(
            x=x, y="p25:Q", y2="p75:Q")
        some = alt.Chart(sample).mark_line(opacity=0.25, strokeWidth=1, color=MAJORELLE).encode(
            x=x, y="total:Q", detail="path:N")
        median = alt.Chart(bands).mark_line(color=MAJORELLE, strokeWidth=3).encode(
            x=x, y="p50:Q",
            tooltip=[alt.Tooltip("date:T", title="Date"),
                     alt.Tooltip("p50:Q", title="Median", format=",.2f"),
                     alt.Tooltip("p5:Q", title="5th percentile", format=",.2f"),
                     alt.Tooltip("p95:Q", title="95th percentile", format=",.2f")])
        line = pd.DataFrame({"budget": [budget]})
        budget_rule = alt.Chart(line).mark_rule(color=ROSE, strokeDash=[6, 4],
                                                strokeWidth=2).encode(y="budget:Q")
        st.altair_chart(alt.layer(outer, inner, some, median, budget_rule).properties(height=340))
        st.caption("Dark line: median path. Shaded bands: middle 50% and middle 90% of simulations. "
                   "Thin lines: 25 individual simulated futures. Dashed line: your budget.")

    with st.expander("How the simulation works"):
        st.markdown(
            "1. **Build the history.** Your expenses are summed per calendar day, from your first "
            "expense to today (%d days). Days with no spending count as 0 MAD.\n"
            "2. **Simulate one future.** For each of the next %d days, one day is drawn at random "
            "from that history, with replacement, and its spending is added up. This is called "
            "bootstrapping: the future is assumed to look like a reshuffled version of your past.\n"
            "3. **Repeat 10,000 times.** Each run gives a different total, because different days "
            "get drawn. Rare big days, like a large one-off purchase, show up only occasionally, "
            "just as they did in reality.\n"
            "4. **Count the outcomes.** The risk is the share of runs where what you've already "
            "spent (%s) plus the simulated spending ends above your budget (%s).\n\n"
            "**Assumptions to keep in mind:** days are drawn independently, so streaks and "
            "seasonality aren't modeled, and the history needs to be representative. A month with "
            "unusual events like travel or Ramadan will shape the simulation. With *Weight recent "
            "weeks more* on, a day's chance of being drawn halves every %d days back in time. "
            "The random seed is fixed so the numbers stay stable, and *Re-run* changes it to show "
            "how little the results move."
            % (len(daily), horizon, fmt(total), fmt(budget), MC_HALF_LIFE))


def page_data(expenses):
    st.markdown("## Data")
    st.caption("Everything is saved automatically to %s." % os.path.abspath(EXPENSES_FILE))
    left, right = st.columns(2, gap="large")

    with left:
        with st.container(border=True):
            st.markdown("#### Back up")
            st.write("Download all %d expenses as a CSV file." % len(expenses))
            st.download_button("Download expenses.csv", csv_bytes(expenses),
                               file_name="expenses.csv", mime="text/csv",
                               disabled=not expenses)
        with st.container(border=True):
            st.markdown("#### Sample data")
            st.write("Adds 60 realistic expenses from the last two months, "
                     "so every chart has something to show.")
            st.button("Load sample data", on_click=load_sample_data)

    with right:
        with st.container(border=True):
            st.markdown("#### Import")
            st.session_state.setdefault("upload_v", 0)
            upload = st.file_uploader("CSV with description, amount, category and date columns",
                                      type="csv", key="upload_%d" % st.session_state["upload_v"])
            if upload is not None:
                valid, skipped, error = parse_uploaded_csv(upload.getvalue())
                if error:
                    st.error(error)
                else:
                    st.write("Found **%d** valid expenses%s." % (
                        len(valid), ", %d rows skipped" % skipped if skipped else ""))
                    mode = st.radio("How to import", ["Add to my expenses", "Replace my expenses"],
                                    horizontal=True)
                    if st.button("Import %d expenses" % len(valid), type="primary",
                                 disabled=not valid):
                        new = valid if mode == "Replace my expenses" else expenses + valid
                        save_expenses(new)
                        st.session_state["upload_v"] += 1
                        notify("Imported %d expenses." % len(valid), "📥")
                        st.rerun()
        with st.container(border=True):
            st.markdown("#### Start over")
            st.write("Remove every expense. Your budget stays as it is.")
            if st.button("Delete all expenses", disabled=not expenses):
                confirm_clear()


# =============================================================================
# App
# =============================================================================
st.set_page_config(page_title="Mizan expense tracker", page_icon="🧾", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

for message, icon in st.session_state.pop("notices", []):
    st.toast(message, icon=icon)

expenses = load_expenses()
budget = load_budget()
total_spent = calculate_total(expenses)
st.session_state.setdefault("menu", PAGES[0])

with st.sidebar:
    st.markdown('<div class="mz-brand">🧾 Mizan</div>'
                '<div class="mz-brand-sub">Personal expense tracker</div>',
                unsafe_allow_html=True)
    st.radio("Menu", PAGES, key="menu", label_visibility="collapsed")
    st.divider()
    if budget:
        used = total_spent / budget
        st.progress(min(used, 1.0))
        if used > 1:
            st.markdown("**Over budget by %s**" % fmt(total_spent - budget))
        else:
            st.markdown("**%s** left of %s" % (fmt(budget - total_spent), fmt(budget)))
    else:
        st.caption("No budget set yet.")
        st.button("Set a budget", on_click=go_to, args=(PAGES[4],))
    st.caption("%d expenses, %s in total" % (len(expenses), fmt(total_spent)))

page = st.session_state["menu"]
if page == PAGES[0]:
    page_dashboard(expenses, budget)
elif page == PAGES[1]:
    page_add(expenses, budget)
elif page == PAGES[2]:
    page_expenses(expenses)
elif page == PAGES[3]:
    page_analytics(expenses)
elif page == PAGES[4]:
    page_budget(expenses, budget)
elif page == PAGES[5]:
    page_risk(expenses, budget)
else:
    page_data(expenses)
