"""
AI SQL Assistant - ask a company database questions in plain English
--------------------------------------------------------------------
Business users ask questions in plain English. The AI (Google Gemini):
  1. reads the database schema, relationships and business rules
  2. writes a SQL query (with JOINs across tables) and picks a chart
DuckDB runs the query (read-only), and the AI explains the result in plain English.

Run locally:  streamlit run app.py
"""

import json
import os
import re
import threading
import time
from datetime import date

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

import database as db

st.set_page_config(page_title="AI SQL Assistant", page_icon="🤖", layout="wide")

# Google Gemini through its OpenAI-compatible endpoint.
# Any OpenAI-compatible provider works (Groq, OpenRouter, OpenAI, ...) - see README.
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Settings and the AI (LLM) connection
# ---------------------------------------------------------------------------

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))  # reads LLM_API_KEY etc.


def get_setting(name, default=None):
    """Read a setting from the .env file, or from the hosting site's secret settings when deployed."""
    if os.getenv(name):
        return os.getenv(name)
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass  # no hosting secrets - that's fine
    return default


def ai_is_configured():
    key = get_setting("LLM_API_KEY")
    return bool(key) and key != "paste-your-key-here"


# Limits that protect your AI credit on a public website (change them in .env)
QUESTIONS_PER_DAY = int(get_setting("QUESTIONS_PER_DAY", 200))  # for the whole website
QUESTIONS_PER_VISITOR = int(get_setting("QUESTIONS_PER_VISITOR", 20))
MAX_QUESTION_LENGTH = 300


@st.cache_resource
def shared_usage():
    """Shared by every visitor: today's AI question count, and answers already given."""
    return {"date": None, "count": 0, "answers": {}, "lock": threading.Lock()}


def take_daily_question():
    """Count one AI question against today's limit. Returns False when the limit is reached."""
    usage = shared_usage()
    with usage["lock"]:
        if usage["date"] != date.today():
            usage["date"], usage["count"] = date.today(), 0
        if usage["count"] >= QUESTIONS_PER_DAY:
            return False
        usage["count"] += 1
        return True


def ask_llm(system_prompt, user_prompt, temperature=0.0):
    """Send one question to the LLM and return its text answer."""
    client = OpenAI(
        api_key=get_setting("LLM_API_KEY"),
        base_url=get_setting("LLM_BASE_URL", DEFAULT_BASE_URL),
    )
    response = client.chat.completions.create(
        model=get_setting("LLM_MODEL", DEFAULT_MODEL),
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# The database
# ---------------------------------------------------------------------------

@st.cache_resource
def get_database():
    """Build the company database once per server and lock it down."""
    con = duckdb.connect()  # in memory
    db.load_into_duckdb(con, db.generate_tables())
    # Safety: queries can't read files or the internet, and can't change these settings
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def run_sql(sql):
    """Run one read-only SELECT query and return the result as a table."""
    statements = duckdb.extract_statements(sql)
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError("Only a single SELECT query is allowed.")
    cursor = get_database().cursor()  # each user gets their own cursor
    try:
        result = cursor.execute(sql).df()
    finally:
        cursor.close()
    for col in result.select_dtypes("datetime").columns:
        if (result[col].dropna().dt.normalize() == result[col].dropna()).all():
            result[col] = result[col].dt.date  # show 2025-09-01, not 2025-09-01 00:00:00
    return result


@st.cache_data
def table_row_counts():
    return {table: run_sql(f"SELECT COUNT(*) FROM {table}").iat[0, 0] for table in db.TABLE_INFO}


@st.cache_data
def column_details(table):
    """Type, key and description of every column, plus the allowed values of short text columns."""
    types = run_sql(f"DESCRIBE {table}").set_index("column_name")["column_type"]
    fks = db.foreign_keys(table)
    rows = []
    for col, description in db.TABLE_INFO[table][1].items():
        key = "PK" if col in db.PRIMARY_KEYS[table] else ""
        if col in fks:
            key = f"{key} FK → {fks[col]}".strip()
        values = ""
        if types[col] == "VARCHAR":
            distinct = run_sql(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL ORDER BY 1 LIMIT 13")[col]
            if len(distinct) <= 12:
                values = ", ".join(f"'{v}'" for v in distinct)
        rows.append({"column": col, "type": types[col], "key": key, "description": description, "values": values})
    return pd.DataFrame(rows)


@st.cache_data
def schema_for_ai():
    """The database described in text - this is what the AI reads before writing SQL."""
    parts = []
    for table, (description, _) in db.TABLE_INFO.items():
        lines = [f"TABLE {table} -- {description}"]
        for c in column_details(table).itertuples():
            extra = f" [{c.key}]" if c.key else ""
            values = f" Values: {c.values}" if c.values else ""
            lines.append(f"  {c.column} {c.type}{extra} -- {c.description}.{values}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Question -> SQL + chart -> answer
# ---------------------------------------------------------------------------

def sql_system_prompt():
    start, end = db.history_window()
    return f"""You are a senior data analyst at {db.COMPANY_NAME}. You write DuckDB SQL for business users who cannot write SQL.

DATABASE SCHEMA ([PK] = primary key, [FK -> table] = foreign key to join on):
{schema_for_ai()}

BUSINESS RULES (always follow these definitions):
{db.business_rules(start, end)}

Reply in exactly this format and nothing else:
```sql
<one SELECT query>
```
```json
{{"chart": "bar|line|pie|scatter|none", "x": "<result column>", "y": "<result column>", "color": "<result column or null>", "title": "<short chart title>"}}
```

SQL rules:
- A single read-only SELECT (WITH ... SELECT is fine). Join tables using the foreign keys above.
- Name result columns in snake_case (e.g. total_revenue). Round money and percentages to 2 decimals.
- Show names (product_name, store_name, ...) instead of only IDs.
- Order results sensibly and LIMIT to 50 rows unless the user asks for more.
- For time trends, group by month with date_trunc('month', <date column>) AS month (or by year / quarter).
- If the database can't answer the question, return SELECT 'This database has no data to answer that question' AS message and chart "none".

Chart rules:
- line: a trend over time (x = the date/month column). Use color to split into groups, e.g. one line per channel.
- bar: comparing categories (x = category name, y = the number).
- pie: share of a total, only when there are 6 or fewer slices.
- scatter: the relationship between two numbers.
- none: a single number, a plain list, or a table with many text columns."""


ANSWER_SYSTEM_PROMPT = """You are a data analyst explaining a query result to a business manager.
Answer the question in 1-3 short sentences using the actual numbers from the result.
Format money like $12,345. Do not mention SQL, tables or queries."""


def parse_reply(text):
    """Split the AI's reply into the SQL query and the chart settings."""
    chart = {}
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if json_match:
        try:
            chart = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
        text = text.replace(json_match.group(0), "")
    sql_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    sql = sql_match.group(1) if sql_match else text
    return sql.strip().rstrip(";").strip(), chart


def answer_question(question, previous=None):
    """Ask the AI for SQL, run it (with one self-correction if it fails) and explain the result."""
    start = time.perf_counter()
    prompt = f"Question: {question}"
    if previous:  # lets people ask follow-ups like "now only for 2025"
        prompt = (f"Previous question: {previous['question']}\nPrevious SQL:\n{previous['sql']}\n"
                  f"(Build on this only if the new question is a follow-up.)\n\n{prompt}")

    sql, chart = parse_reply(ask_llm(sql_system_prompt(), prompt))
    failed_attempt = None
    try:
        result = run_sql(sql)
    except Exception as error:
        # Show the AI its mistake and let it fix the query once
        failed_attempt = {"sql": sql, "error": str(error)}
        retry = f"{prompt}\n\nThis query failed:\n```sql\n{sql}\n```\nError: {error}\n\nFix the query."
        sql, chart = parse_reply(ask_llm(sql_system_prompt(), retry))
        result = run_sql(sql)

    answer = ask_llm(
        ANSWER_SYSTEM_PROMPT,
        f"Question: {question}\n\nResult ({len(result)} rows):\n{result.head(50).to_string(index=False)}",
        temperature=0.2,
    )
    return {
        "question": question,
        "sql": sql,
        "chart": chart,
        "result": result,
        "answer": answer,
        "failed_attempt": failed_attempt,
        "seconds": round(time.perf_counter() - start, 1),
    }


def tables_used(sql):
    return [t for t in db.TABLE_INFO if re.search(rf"\b{t}\b", sql, re.IGNORECASE)]


def make_chart(result, spec):
    """Draw the chart the AI asked for, if it fits the result."""
    kind = (spec or {}).get("chart", "none")
    x, y, color = spec.get("x"), spec.get("y"), spec.get("color")
    if kind == "none" or len(result) < 2 or x not in result.columns or y not in result.columns:
        return None
    if not pd.api.types.is_numeric_dtype(result[y]):
        return None
    color = color if color in result.columns and color not in (x, y) else None
    title = spec.get("title")

    if kind == "line":
        fig = px.line(result.sort_values(x), x=x, y=y, color=color, markers=True, title=title)
    elif kind == "pie" and len(result) <= 8:
        fig = px.pie(result, names=x, values=y, title=title, hole=0.4)
    elif kind == "scatter":
        fig = px.scatter(result, x=x, y=y, color=color, title=title, hover_data=result.columns)
    else:
        fig = px.bar(result.head(30), x=x, y=y, color=color, title=title, barmode="group")
    fig.update_layout(margin=dict(t=50, l=10, r=10, b=10), legend_title_text="")
    return fig


def escape_dollars(text):
    """Streamlit reads text between two $ signs as a math formula, so escape them."""
    return text.replace("$", "\\$")


def pretty_number(value):
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

with st.spinner("Loading the company database..."):
    get_database()
counts = table_row_counts()

with st.sidebar:
    st.header(f"🏢 {db.COMPANY_NAME}")
    st.caption("Demo company database (realistic generated data)")
    c1, c2 = st.columns(2)
    c1.metric("Tables", len(counts))
    c2.metric("Rows", f"{sum(counts.values()):,}")
    st.metric("Orders", f"{counts['orders']:,}")

    st.header("🤖 AI")
    if ai_is_configured():
        st.success(f"Connected: {get_setting('LLM_MODEL', DEFAULT_MODEL)}")
    else:
        st.warning("No API key set. Add LLM_API_KEY to the .env file (see README).")
    if st.button("🗑️ Clear conversation", width="stretch"):
        st.session_state.history = []

st.title("🤖 AI SQL Assistant")
st.markdown("##### Ask your company database questions in plain English")
st.caption(
    f"Ask anything about {db.COMPANY_NAME}'s sales, customers, products, stores and staff, no SQL needed. "
    "The AI writes the SQL, the database runs it, and you get a chart and a plain-English answer."
)

tab_ask, tab_schema = st.tabs(["💬 Ask a question", "🗂️ Database & relationships"])

# --- Tab 1: Ask a question ------------------------------------------------------
with tab_ask:
    st.session_state.setdefault("history", [])
    history = st.session_state.history

    if not ai_is_configured():
        st.info("Add an LLM_API_KEY to start asking questions (see README).")
    else:
        with st.form("question_form", clear_on_submit=True):
            question = st.text_input(
                "Your question",
                placeholder="e.g. Which store had the highest profit last year?",
            )
            submitted = st.form_submit_button("Ask", type="primary")
        is_example = False
        if history:
            st.caption("💡 Follow-up questions work too, e.g. *\"now show only 2025\"* or *\"split it by channel\"*.")

        examples = [
            "Show monthly revenue for the last 12 months by channel",
            "Which 10 products made the most profit last year?",
            "Which product category has the highest return rate?",
            "Top 5 sales associates by revenue this year, with their store",
            "What share of revenue comes from each loyalty tier?",
            "Which store had the highest average order value?",
            "Revenue and profit margin by region last year",
            "How many new customers signed up each month this year?",
        ]
        with st.expander("Example questions", expanded=not history):
            grid = st.columns(2)
            for i, example in enumerate(examples):
                if grid[i % 2].button(example, key=f"example_{i}", width="stretch"):
                    question, submitted, is_example = example, True, True

        question = " ".join(question.split())
        # Typed questions can be follow-ups; example questions always stand alone
        previous = history[0] if history and not is_example else None
        # Same question (and same previous question) as someone before -> reuse that answer for free
        cache_key = (question.lower(), previous and previous["sql"])
        answers = shared_usage()["answers"]
        asked = st.session_state.setdefault("questions_asked", 0)

        if submitted and question:
            if cache_key in answers:
                history.insert(0, dict(answers[cache_key], question=question, seconds=0.0))
            elif len(question) > MAX_QUESTION_LENGTH:
                st.warning(f"Please keep questions under {MAX_QUESTION_LENGTH} characters.")
            elif asked >= QUESTIONS_PER_VISITOR:
                st.warning(f"You've reached the demo limit of {QUESTIONS_PER_VISITOR} questions for this visit. "
                           "Thanks for trying it!")
            elif not take_daily_question():
                st.warning("This demo has reached its daily question limit. Please come back tomorrow, "
                           "or try the example questions.")
            else:
                with st.spinner("The AI is writing SQL..."):
                    try:
                        item = answer_question(question, previous)
                        st.session_state.questions_asked += 1
                        history.insert(0, item)
                        if len(answers) < 500:
                            answers[cache_key] = item
                    except Exception as error:
                        st.error(f"Sorry, I couldn't answer that. ({error})")
        left = max(QUESTIONS_PER_VISITOR - st.session_state.questions_asked, 0)
        st.caption(f"Demo limit: {left} of {QUESTIONS_PER_VISITOR} questions left in this visit.")

    for n, item in enumerate(history):
        result = item["result"]
        st.divider()
        st.markdown(f"### ❓ {item['question']}")

        # The answer and chart come first: that's what a business user cares about
        st.success(escape_dollars(item["answer"]))
        if result.shape == (1, 1):
            st.metric(result.columns[0].replace("_", " ").title(), pretty_number(result.iat[0, 0]))
        else:
            chart = make_chart(result, item["chart"])
            if chart is not None:
                st.plotly_chart(chart, width="stretch", key=f"chart_{len(history) - n}")
            st.dataframe(result, hide_index=True, width="stretch")

        # How the answer was made: for anyone who wants to check the work
        used = tables_used(item["sql"])
        with st.expander(f"🔍 SQL written by the AI · {len(used)} tables joined: {', '.join(used)} · "
                         f"{len(result):,} rows · {item['seconds']} s"):
            if item["failed_attempt"]:
                st.warning("The first query failed, so the AI read the error and fixed it.")
                st.code(item["failed_attempt"]["sql"], language="sql")
                st.caption(f"Error: {item['failed_attempt']['error']}")
                st.markdown("**Corrected query:**")
            st.code(item["sql"], language="sql")

# --- Tab 2: Database & relationships ------------------------------------------
with tab_schema:
    st.subheader("How the tables connect")
    st.caption("Each line joins a foreign key (FK) to the primary key (PK) it points to. "
               "A bar marks the \"one\" side and a crow's foot the \"many\" side: one customer has many orders.")
    st.graphviz_chart(db.er_diagram_dot(), width="stretch")

    with st.expander("📏 Business rules the AI follows (how metrics are defined)"):
        st.markdown(db.business_rules(*db.history_window()))

    st.subheader("Tables")
    overview = pd.DataFrame([
        {"table": t, "rows": counts[t], "description": d} for t, (d, _) in db.TABLE_INFO.items()
    ])
    st.dataframe(overview, hide_index=True, width="stretch")

    table = st.selectbox("Look inside a table", list(db.TABLE_INFO))
    st.dataframe(column_details(table), hide_index=True, width="stretch")
    st.dataframe(run_sql(f"SELECT * FROM {table} LIMIT 50"), hide_index=True, width="stretch")
