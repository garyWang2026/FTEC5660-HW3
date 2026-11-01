#!/usr/bin/env python3
"""FTEC5660 HW3 student starter: an agent that applies 3 of Fisher's 15 points using tools."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sqlite3
import threading
import zlib
from pathlib import Path
from typing import Any


MODEL_NAME = "deepseek-v4-flash"
INTERVIEW_LIMIT = 10
MAX_SQL_ROWS = 50

# Philip Fisher, "Common Stocks and Uncommon Profits", Part One, Chapter 3.
# For every point, PASS means the company looks good on it. You choose 3
# points and decide yourself what PASS means for each of them.
FISHER_POINTS = {
    1: "Does the company have products or services with sufficient market potential to make possible a sizable increase in sales for at least several years?",
    2: "Does the management have a determination to continue to develop products or processes that will still further increase total sales potentials when the growth potentials of currently attractive product lines have largely been exploited?",
    3: "How effective are the company's research and development efforts in relation to its size?",
    4: "Does the company have an above-average sales organization?",
    5: "Does the company have a worthwhile profit margin?",
    6: "What is the company doing to maintain or improve profit margins?",
    7: "Does the company have outstanding labor and personnel relations?",
    8: "Does the company have outstanding executive relations?",
    9: "Does the company have depth to its management?",
    10: "How good are the company's cost analysis and accounting controls?",
    11: "Are there other aspects of the business, somewhat peculiar to the industry involved, which will give the investor important clues as to how outstanding the company may be in relation to its competition?",
    12: "Does the company have a short-range or long-range outlook in regard to profits?",
    13: "In the foreseeable future will the growth of the company require sufficient equity financing so that the larger number of shares then outstanding will largely cancel the existing stockholders' benefit from this anticipated growth?",
    14: "Does the management talk freely to investors about its affairs when things are going well but 'clam up' when troubles and disappointments occur?",
    15: "Does the company have a management of unquestionable integrity?",
}
VERDICTS = ("PASS", "FAIL")


def load_env_file(path: Path = Path(".env")) -> None:
    """Load the simple KEY=VALUE entries used by this homework."""
    if not path.is_file():
        return
    import os

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


# Choose any 3 of the 15 points, e.g. CHOSEN_POINTS = [1, 7, 15]. Your agent
# gives a PASS or FAIL verdict on these 3 points only, with your own rule for each.
CHOSEN_POINTS: list[int] = [3, 5, 13]  ### YOUR CODE HERE


# Rules we designed for the three chosen points. Every number used below comes
# from the company's own SQL database via the sql_query tool (never from direct
# file access); the medians are the per-industry medians in industry_medians.
#   Point 3  - R&D effectiveness: FY2025 sales of products launched since 2023,
#              divided by R&D spent in 2023-2025, vs the industry-median
#              new-product-sales-per-R&D-dollar.
#   Point 5  - Profit margin: FY2025 operating margin (revenue minus COGS, SGA
#              and R&D over revenue) vs the industry-median operating margin.
#   Point 13 - Growth without dilutive financing: cash at the end of 2026Q2 plus
#              the operating cash flow of the most recent 12 quarters, vs the
#              planned capex for 2026-2028.
_POINT_RULES = {
    3: "PASS when FY2025 sales of products launched since 2023, divided by total R&D spent in 2023-2025, "
       "is above the industry-median new-product-sales-per-R&D-dollar.",
    5: "PASS when the FY2025 operating margin (revenue minus cost of sales, selling & admin and R&D, over revenue) "
       "is at or above the industry-median operating margin.",
    13: "PASS when cash at the end of 2026Q2 plus the operating cash flow of the most recent 12 quarters "
        "covers the total planned capex for 2026-2028.",
}

_SQL = {
    "np_per_rd": (
        "SELECT "
        "(SELECT COALESCE(SUM(o.amount),0) FROM orders o JOIN products p ON o.product=p.product "
        "WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND p.launch_date >= '2023-01-01') * 1.0 "
        "/ "
        "(SELECT COALESCE(SUM(research_development),0) FROM monthly_costs "
        "WHERE month BETWEEN '2023-01' AND '2025-12')"
    ),
    "med_per_rd": (
        "SELECT new_product_sales_per_rd FROM industry_medians "
        "WHERE industry=(SELECT industry FROM company)"
    ),
    "opm": (
        "SELECT "
        "((SELECT COALESCE(SUM(amount),0) FROM orders WHERE order_date BETWEEN '2025-01-01' AND '2025-12-31') "
        "- (SELECT COALESCE(SUM(cost_of_sales),0) FROM monthly_costs WHERE month BETWEEN '2025-01' AND '2025-12') "
        "- (SELECT COALESCE(SUM(selling_admin),0) FROM monthly_costs WHERE month BETWEEN '2025-01' AND '2025-12') "
        "- (SELECT COALESCE(SUM(research_development),0) FROM monthly_costs WHERE month BETWEEN '2025-01' AND '2025-12')) * 100.0 "
        "/ "
        "(SELECT COALESCE(SUM(amount),0) FROM orders WHERE order_date BETWEEN '2025-01-01' AND '2025-12-31')"
    ),
    "med_opm": (
        "SELECT operating_margin_pct FROM industry_medians "
        "WHERE industry=(SELECT industry FROM company)"
    ),
    "cash_plus_ocf12": (
        "SELECT "
        "(SELECT cash_end FROM quarterly_cash WHERE quarter='2026Q2') "
        "+ (SELECT COALESCE(SUM(operating_cash_flow),0) FROM "
        "(SELECT operating_cash_flow FROM quarterly_cash ORDER BY quarter DESC LIMIT 12))"
    ),
    "capex_total": "SELECT COALESCE(SUM(planned_capex),0) FROM capex_plan",
}


def build_agent() -> Any:
    """Create and return your model or agent once.

    The agent is the DeepSeek model named by ``MODEL_NAME``; the verdicts on
    the three chosen points are computed deterministically from the company's
    database (through the four tools), and the model writes each company's
    two-or-three-sentence summary explaining the verdicts.
    """
    import os

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=MODEL_NAME,
        temperature=0.0,
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    )


def _sql_value(tool: Any, query: str) -> float:
    """Run one SQL query through the sql_query tool and return the first value."""
    result = tool.invoke({"query": query})
    text = result if isinstance(result, str) else str(result)
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("...") or line == "(no rows)":
            continue
        try:
            return float(line.split("|")[0].strip())
        except ValueError:
            continue
    raise ValueError(f"Could not parse sql_query result: {text[:300]}")


def _verdicts(tools: list[Any]) -> tuple[dict[int, str], dict[str, float]]:
    """Compute the three verdicts from the database, using only the tools."""
    sql = tools[2]  # list_documents, read_document, sql_query, interview
    np_per_rd = _sql_value(sql, _SQL["np_per_rd"])
    med_per_rd = _sql_value(sql, _SQL["med_per_rd"])
    opm = _sql_value(sql, _SQL["opm"])
    med_opm = _sql_value(sql, _SQL["med_opm"])
    cash_plus_ocf = _sql_value(sql, _SQL["cash_plus_ocf12"])
    capex = _sql_value(sql, _SQL["capex_total"])

    points = {
        3: "PASS" if np_per_rd > med_per_rd else "FAIL",
        5: "PASS" if opm >= med_opm else "FAIL",
        13: "PASS" if cash_plus_ocf > capex else "FAIL",
    }
    numbers = {
        "np_per_rd": np_per_rd,
        "med_per_rd": med_per_rd,
        "opm": opm,
        "med_opm": med_opm,
        "cash_plus_ocf": cash_plus_ocf,
        "capex": capex,
    }
    return points, numbers


async def _summary(agent: Any, name: str, points: dict[int, str], numbers: dict[str, float]) -> str:
    """Ask the model for a 2-3 sentence analyst-style explanation of the verdicts."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        detail = "\n".join([
            f"Point 3 (R&D effectiveness) {points[3]}: new-product sales per R&D dollar "
            f"{numbers['np_per_rd']:.2f} vs industry median {numbers['med_per_rd']:.2f}.",
            f"Point 5 (profit margin) {points[5]}: FY2025 operating margin "
            f"{numbers['opm']:.1f}% vs industry median {numbers['med_opm']:.1f}%.",
            f"Point 13 (growth without dilution) {points[13]}: cash + 12-quarter operating cash flow "
            f"{numbers['cash_plus_ocf']:.0f}k vs planned 2026-2028 capex {numbers['capex']:.0f}k.",
        ])
        msg = await agent.ainvoke([
            SystemMessage(content="You are a financial analyst applying Philip Fisher's 15-point checklist. "
                                  "Explain the verdicts concisely, as an analyst would."),
            HumanMessage(content=f"Company {name}. Verdicts: {detail}\n"
                                 "Write 2-3 sentences explaining why each point passes or fails."),
        ])
        text = str(getattr(msg, "content", "")).strip()
        if text:
            return text[:700]
    except Exception:
        pass
    fallback = "; ".join(f"point {p}: {v}" for p, v in sorted(points.items()))
    return f"{name} — {fallback}."


async def analyze_companies(agent: Any, companies: dict[str, list[Any]]) -> dict[str, dict[str, Any]]:
    """Run your agent and return its verdicts on CHOSEN_POINTS for every company.

    ``companies`` maps each company folder name to its four LangChain tools:

        list_documents()             names and dates of the company's documents
        read_document(name)          the text of one document
        sql_query(query)             one read-only SQLite query on company.db
        interview(role, topic)       one interview answer (INTERVIEW_LIMIT per company)

    Give the tools to a tool-calling agent, e.g.
    ``create_agent(model, tools=companies[name], system_prompt=...)``, or call
    them yourself with ``tool.invoke({...})``. The README explains the
    documents, the database tables and the interview roles and topics.

    Return one dictionary per company folder name, e.g. with
    CHOSEN_POINTS = [1, 7, 15]:

        {
            "hollins_group": {
                "points": {1: "PASS", 7: "FAIL", 15: "PASS"},
                "summary": "Two or three sentences explaining the verdicts.",
            },
            ...
        }

    Each chosen point needs a verdict ("PASS" or "FAIL"; True/False also
    works). Other points are ignored.

    Catch errors per company (e.g. a failed API call) and still return an
    entry for it: an exception here means no results.csv, which scores zero.
    You may analyse companies in parallel (e.g. ``asyncio.gather``).
    """
    async def analyze_one(name: str, tools: list[Any]) -> tuple[str, dict[str, Any]]:
        points: dict[int, str] = {}
        numbers: dict[str, float] = {}
        try:
            points, numbers = _verdicts(tools)
            summary = await _summary(agent, name, points, numbers)
        except Exception as exc:  # noqa: BLE001 - keep results.csv for every company
            summary = (f"Evaluation error for {name}: {exc}. "
                       f"Partial verdicts: {', '.join(f'point {p}: {v}' for p, v in sorted(points.items())) or 'none'}.")
        return name, {"points": points, "summary": summary}

    results = await asyncio.gather(*(analyze_one(name, tools) for name, tools in companies.items()))
    return {name: entry for name, entry in results}


# Everything below is provided runner/scoring code. No edits are needed.
# Your code must read company data only through these tools: do not open
# company.db or interviews.dat directly.

INTERVIEWS_USED: dict[str, int] = {}


def company_folders(folder: Path) -> list[Path]:
    """Return one sub-folder per company directly inside *folder*, sorted by name."""
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def make_tools(company_folder: Path) -> list[Any]:
    """Build the four tools for one company."""
    from langchain_core.tools import tool

    name = company_folder.name
    db_uri = f"{(company_folder / 'company.db').resolve().as_uri()}?mode=ro"
    answers = json.loads(zlib.decompress((company_folder / "interviews.dat").read_bytes()))
    documents = {p.name: p for p in sorted(company_folder.glob("*.md"))}
    lock = threading.Lock()
    INTERVIEWS_USED[name] = 0

    @tool
    def list_documents() -> str:
        """List this company's documents (annual letter, earnings calls, news) with their dates."""
        lines = []
        for doc_name, path in documents.items():
            text = path.read_text(encoding="utf-8").splitlines()
            dated = next((line for line in text if line.startswith("Date:")), "")
            lines.append(f"{doc_name}: {text[0].lstrip('# ')} ({dated or 'undated'})")
        return "\n".join(lines)

    @tool
    def read_document(name: str) -> str:
        """Return the full text of one document named by list_documents, e.g. 'annual_letter_2025.md'."""
        path = documents.get(name.strip())
        if path is None:
            return f"No document named {name!r}. Available: {', '.join(documents)}"
        return path.read_text(encoding="utf-8")

    @tool
    def sql_query(query: str) -> str:
        """Run one read-only SQLite query on this company's database and return at most 50 rows.

        Amounts are in USD thousands. Dates are 'YYYY-MM-DD', months 'YYYY-MM', quarters like '2025Q3'.
        Tables:
          company(name, industry)
          industry_medians(industry, revenue_growth_2y_pct, new_product_share_pct, new_product_sales_per_rd, operating_margin_pct)
          orders(order_id, order_date, product, customer, amount, note)
          products(product, launch_date)
          monthly_costs(month, cost_of_sales, selling_admin, research_development)
          quarterly_cash(quarter, operating_cash_flow, capex, cash_end)
          capex_plan(year, planned_capex)
          returns(month, units_shipped, units_returned)
          insider_trades(trade_date, person, title, side, shares, price)
        Use SUM, GROUP BY and WHERE to compute totals rather than reading raw rows.
        """
        try:
            con = sqlite3.connect(db_uri, uri=True)
            try:
                cursor = con.execute(query)
                columns = [c[0] for c in cursor.description or []]
                rows = cursor.fetchmany(MAX_SQL_ROWS + 1)
            finally:
                con.close()
        except sqlite3.Error as exc:
            return f"SQL error: {exc}"
        if not columns:
            return "Query returned no columns."
        fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)  # noqa: E731
        out = [" | ".join(columns)] + [" | ".join(fmt(v) for v in row) for row in rows[:MAX_SQL_ROWS]]
        if len(rows) > MAX_SQL_ROWS:
            out.append(f"... more rows not shown (limit {MAX_SQL_ROWS}); aggregate or add LIMIT/OFFSET.")
        if not rows:
            out.append("(no rows)")
        return "\n".join(out)

    @tool
    def interview(role: str, topic: str) -> str:
        """Interview one person about the company (at most 10 interviews per company).

        role: customer, current_employee, former_employee, competitor or supplier.
        topic: sales_team, working_conditions, top_management, decision_making or competitive_edge.
        People who would not know about a topic say so; the README lists who knows what.
        """
        role, topic = role.strip().lower(), topic.strip().lower()
        if role not in answers:
            return f"Unknown role {role!r}. Roles: {', '.join(answers)}. (Not counted.)"
        if topic not in answers[role]:
            return f"Unknown topic {topic!r}. Topics: {', '.join(answers[role])}. (Not counted.)"
        with lock:
            if INTERVIEWS_USED[name] >= INTERVIEW_LIMIT:
                return f"Interview limit reached: {INTERVIEW_LIMIT} interviews per company."
            INTERVIEWS_USED[name] += 1
        return answers[role][topic]

    return [list_documents, read_document, sql_query, interview]


def normalize_verdict(value: Any) -> str | None:
    """Accept PASS/FAIL (any case) or a boolean."""
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    text = str(getattr(value, "content", value)).strip().upper()
    return text if text in VERDICTS else None


def check_chosen_points(chosen: Any) -> list[int]:
    """CHOSEN_POINTS must name 3 different points between 1 and 15."""
    try:
        points = sorted({int(p) for p in chosen})
    except (TypeError, ValueError):
        points = []
    if len(points) != 3 or len(chosen) != 3 or not all(p in FISHER_POINTS for p in points):
        raise SystemExit("Set CHOSEN_POINTS at the top of hw3.py to 3 different point numbers "
                         f"between 1 and 15, e.g. [1, 7, 15] (now: {chosen!r}).")
    return points


def normalize_points(points: Any, chosen: list[int]) -> dict[int, str | None]:
    """Map each chosen point number to PASS/FAIL, or None when missing/invalid."""
    points = points if isinstance(points, dict) else {}
    by_number: dict[int, Any] = {}
    for key, value in points.items():
        try:
            by_number[int(key)] = value
        except (TypeError, ValueError):
            continue
    return {p: normalize_verdict(by_number.get(p)) for p in chosen}


def read_ground_truth(folder: Path) -> dict[str, dict[str, Any]]:
    """Read the expected 15 point verdicts per company."""
    path = folder / "ground_truth.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def point_errors(points: dict[int, str | None], expected: dict[str, Any] | None) -> tuple[int, str]:
    """Count correct point verdicts and describe the wrong ones."""
    if expected is None:
        return 0, ""
    wrong = []
    for p in points:
        truth = expected["points"][str(p)]
        if points[p] != truth:
            wrong.append(f"{p}: expected {truth}, predicted {points[p] or 'missing'}")
    if all(v is None for v in points.values()):
        return 0, "all point verdicts missing"
    return len(points) - len(wrong), "; ".join(wrong)


def balanced_point_accuracy(
    analyses: dict[str, Any], truth: dict[str, dict[str, Any]], names: list[str], chosen: list[int]
) -> float:
    """Mean of the accuracy on true-PASS points and on true-FAIL points.

    Most verdicts are PASS, so answering PASS everywhere gets a high plain
    accuracy but only 50% balanced accuracy. Grading uses the balanced number.
    """
    hits = {"PASS": [0, 0], "FAIL": [0, 0]}
    for name in names:
        if name not in truth:
            continue
        entry = analyses.get(name)
        points = normalize_points(entry.get("points") if isinstance(entry, dict) else None, chosen)
        for p in chosen:
            expected = truth[name]["points"][str(p)]
            hits[expected][0] += points[p] == expected
            hits[expected][1] += 1
    rates = [h / n for h, n in hits.values() if n]
    return sum(rates) / len(rates) if rates else 0.0


def write_results(
    names: list[str], analyses: dict[str, Any], truth: dict[str, dict[str, Any]], chosen: list[int]
) -> tuple[Path, int]:
    """Write results.csv and return the number of correct point verdicts."""
    output = Path("results.csv")
    correct_points = 0
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "points", "points_correct", "point_errors", "interviews_used", "summary"])
        for name in names:
            entry = analyses.get(name)
            entry = entry if isinstance(entry, dict) else {}
            points = normalize_points(entry.get("points"), chosen)
            expected = truth.get(name)
            n_points, errors = point_errors(points, expected)
            correct_points += n_points
            writer.writerow([
                name,
                " ".join(f"{p}:{points[p] or 'missing'}" for p in chosen),
                f"{n_points}/{len(chosen)}" if expected else "",
                errors,
                INTERVIEWS_USED.get(name, 0),
                str(entry.get("summary", "")).strip(),
            ])
    return output, correct_points


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FTEC5660 HW3 on company data folders")
    parser.add_argument(
        "--data-folder",
        required=True,
        type=Path,
        help="folder containing one sub-folder per company",
    )
    return parser.parse_args()


async def run(folder: Path) -> int:
    folders = company_folders(folder)
    if not folders:
        raise SystemExit(f"no company folders found in {folder}")

    chosen = check_chosen_points(CHOSEN_POINTS)
    load_env_file()
    companies = {path.name: make_tools(path) for path in folders}
    agent = build_agent()
    analyses = await analyze_companies(agent, companies)
    if not isinstance(analyses, dict):
        raise TypeError("analyze_companies() must return a dictionary")

    truth = read_ground_truth(folder)
    output, correct_points = write_results(list(companies), analyses, truth, chosen)
    summary = f" Your points: {', '.join(map(str, chosen))}."
    if truth:
        summary += (
            f" Point accuracy: {correct_points}/{len(companies) * len(chosen)}"
            f" (balanced: {balanced_point_accuracy(analyses, truth, list(companies), chosen):.1%})."
        )
    print(f"Processed {len(companies)} compan{'y' if len(companies) == 1 else 'ies'}. Wrote {output}.{summary}")
    return 0


def main() -> int:
    args = parse_args()
    if not args.data_folder.is_dir():
        raise SystemExit(f"not a folder: {args.data_folder}")
    return asyncio.run(run(args.data_folder))


if __name__ == "__main__":
    raise SystemExit(main())
