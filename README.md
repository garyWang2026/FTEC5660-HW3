# FTEC5660 Homework 3: Fisher's 15-Point Investment Agent

Build a LangChain agent that researches a company with tools and applies the
framework from Philip Fisher's *Common Stocks and Uncommon Profits* (Part One,
Chapter 3 "What to buy: the fifteen points to look for in a common stock", and
Chapter 4 "What to buy: applying this to your own needs"). You choose 3 of
Fisher's 15 points and decide yourself what PASS means for each. For every
company your agent gives a PASS/FAIL verdict on your 3 points and a short
summary.

The companies are fictional, so the model cannot answer from memory. Unlike a
pile of reports, the evidence is spread over three sources, and your agent has
to go and get it with tools, the way Fisher's "scuttlebutt" method sends an
investor to talk to customers, competitors, suppliers and staff.

## Data and tools

`public_test/` has one folder per company. Your code receives four tools per
company (built by the provided code in `hw3.py`):

| Tool | What it gives you |
| --- | --- |
| `list_documents()` | the company's six documents and their dates |
| `read_document(name)` | one document: the 2025 letter to shareholders, four earnings calls (Q3 2025 to Q2 2026) and a news file (July 2025 to July 2026) |
| `sql_query(query)` | one read-only SQLite query on the company's database; at most 50 rows come back, so use `SUM`, `GROUP BY` and `WHERE` |
| `interview(role, topic)` | what one person says about the company; at most **10 interviews per company** |

The documents are what management says. Management's own claims (such as "we
have never cut research" or "our people are our greatest strength") are not
evidence on their own: check them against the database and the interviews.

**Database tables** (amounts in USD thousands; dates `YYYY-MM-DD`, months
`YYYY-MM`, quarters like `2025Q3`; the fiscal year is the calendar year):

| Table | Columns |
| --- | --- |
| `company` | name, industry |
| `industry_medians` | industry, revenue_growth_2y_pct, new_product_share_pct, new_product_sales_per_rd, operating_margin_pct (one row per industry; use the row for the company's own industry) |
| `orders` | order_id, order_date, product, customer, amount, note (about 3,000 to 4,000 orders from January 2023 to June 2026; revenue is the sum of order amounts) |
| `products` | product, launch_date |
| `monthly_costs` | month, cost_of_sales, selling_admin, research_development |
| `quarterly_cash` | quarter, operating_cash_flow, capex, cash_end |
| `capex_plan` | year, planned_capex (2026 to 2028) |
| `returns` | month, units_shipped, units_returned |
| `insider_trades` | trade_date, person, title, side (`buy` or `sell`), shares, price |

**Terms used in the data.**

| Term | Meaning |
| --- | --- |
| FY2025 | Fiscal year 2025. Here the fiscal year is the calendar year, so FY2025 is January to December 2025. |
| Quarter | Three months of the year: Q1 is January to March, Q2 April to June, Q3 July to September and Q4 October to December. The database writes `2025Q3`; the documents write "third quarter 2025". |
| Amounts | The database is in **USD thousands** (676,100 means US$676.1 million). The documents use USD millions. |
| Revenue | Money from sales: the sum of `amount` in `orders`. |
| Cost of sales | The cost of making the products that were sold. |
| Selling and admin | The cost of selling and of running the company (sales staff, offices, management). |
| R&D | Research and development spending, mainly on new products. |
| Operating margin | Operating profit as a share of revenue: (revenue − cost of sales − selling and admin − R&D) ÷ revenue. |
| Operating cash flow | Cash that the day-to-day business brings in during a quarter. |
| Cash at the end of a quarter | The cash the company holds on the last day of that quarter (`cash_end`). |
| Capex | Capital expenditure: spending on factories, machines and other long-term assets. `capex_plan` holds the planned capex for 2026 to 2028. |
| Return rate | Units returned ÷ units shipped, from the `returns` table. |
| Industry median | The middle value for companies in the same industry, from `industry_medians`. |
| Insider | A director or senior manager of the company. `insider_trades` lists the shares they bought (`buy`) or sold (`sell`). |
| Earnings call | A meeting each quarter where management presents the quarter's results to investors. Each call quotes that quarter's revenue. |

**Interviews.** Roles: `customer`, `current_employee`, `former_employee`,
`competitor`, `supplier`. Topics: `sales_team`, `working_conditions`,
`top_management`, `decision_making`, `competitive_edge`. Only some people know
about each topic; the others say they can't comment, and that answer still
uses up one interview.

| Topic | Who knows about it |
| --- | --- |
| `sales_team` | customer, competitor |
| `working_conditions` | current_employee, former_employee |
| `top_management` | former_employee, supplier |
| `decision_making` | supplier, customer |
| `competitive_edge` | competitor, customer |

People who know about a topic always agree with each other, so one good answer
is enough.

## Choose your 3 points and your rules

Pick any 3 of Fisher's 15 points and write them in `CHOSEN_POINTS` near the
top of `hw3.py`, e.g. `CHOSEN_POINTS = [1, 7, 15]`. The full questions are in
`FISHER_POINTS` in `hw3.py` and in the book.

| # | Fisher's point | Where the evidence is |
| --- | --- | --- |
| 1 | Market potential for sales growth | database |
| 2 | New products as current lines mature | database |
| 3 | Effective research and development | database |
| 4 | Above-average sales organization | interviews (`sales_team`) |
| 5 | Worthwhile profit margin | database |
| 6 | Maintaining or improving margins | database |
| 7 | Labour and personnel relations | interviews (`working_conditions`) |
| 8 | Executive relations | interviews (`top_management`) |
| 9 | Depth of management | interviews (`decision_making`) |
| 10 | Cost analysis and accounting controls | earnings calls, checked against the database |
| 11 | Advantage over competitors | interviews (`competitive_edge`) |
| 12 | Long-range outlook on profits | database |
| 13 | Growth without dilutive equity financing | database |
| 14 | Management talks freely about troubles | earnings calls, checked against the database |
| 15 | Management of unquestionable integrity | news file, checked against the database |

For each of your points, **you design the rule**: which evidence to use, what
to compute or whom to ask, and where the line between PASS and FAIL lies. PASS
means the company looks favourable on that point, as Fisher would see it.

We grade your verdicts against our own answer key. It uses one fixed rule per
point, which we do not publish, and the data never puts a company close to
the line of that rule, so a sensible reading of Fisher usually gives the same
answer. **Test your rules on the public answers**:
`public_test/ground_truth.json` gives the expected verdict on all 15 points
for each of the 20 public companies, and every point fails in 6 of them. If
your rule disagrees with the public answers, rethink it.

**Tip: calculate with tools, not in your head.** Do every sum, ratio and
comparison in SQL or Python, including the number of days between two dates
(SQLite's `julianday()` gives a date as a number of days).

## Student task

Fill in the three places in `hw3.py` marked `### YOUR CODE HERE`. You may add
imports, constants and helper functions above them, but do not change the
provided code below them:

- `CHOSEN_POINTS` lists your 3 points.
- `build_agent()` creates your model and anything else you need once.
- `analyze_companies(agent, companies)` receives
  `{company_folder: [list_documents, read_document, sql_query, interview]}`
  and returns, for every company,
  `{"points": {1: "PASS", 7: "FAIL", 15: "PASS"}, "summary": "..."}` (here with
  `CHOSEN_POINTS = [1, 7, 15]`).

Use the course techniques that fit your points: tool use for the database and
the interviews, planning which interviews to spend, routing each point to the
right source, prompt chaining, parallel calls, reflection to check your
answers, or a combination. Your code must read company data **only through
the four tools**; do not open `company.db` or `interviews.dat` yourself. Do
not hard-code folder names, company names or the public answers.

## Setup and public test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=your_key_here" > .env
python3 hw3.py --data-folder public_test
```

Use your own DeepSeek API key (from https://platform.deepseek.com). The
required model is `deepseek-v4-flash`. We grade with our own key, so never put
a key in your code; `.env` must stay out of git.

The program creates `results.csv` with the columns `company`, `points`,
`points_correct`, `point_errors`, `interviews_used` and `summary`, and prints
the point score on your 3 points (the percentage after "balanced"). The point
score is the average of two shares: the share of truly passing verdicts that
you marked PASS and the share of truly failing verdicts that you marked FAIL.
For example, 90% and 60% give (90% + 60%) / 2 = 75%, and marking every point
PASS gives (100% + 0%) / 2 = 50%. Once `CHOSEN_POINTS` is set, the starter
runs before you add any API code (it returns no verdicts, so it scores 0%).

`public_test/ground_truth.json` gives the expected verdicts on all 15 points
for each public company. Grading uses a private set of about 20 unseen
companies with the same tools and the same answer key rules, but different
names and wording, and scores your 3 points only.

## Homework 3 solution:

### My 3 points and rules

I chose **points 3, 5 and 13**, the three database-only points on the list.
Fisher's own words for point 3 ask *"how effective are the company's research
and development efforts in relation to its size?"*, point 5 asks *"does the
company have a worthwhile profit margin?"*, and point 13 asks whether *"the
growth of the company"* will require *"sufficient equity financing"* that would
dilute existing stockholders. All three can be answered with hard numbers from
`company.db` through `sql_query`, which makes the agent fast, deterministic and
easy to verify — no interviews to spend, no documents to read, and no model
arithmetic (the most common cause of wrong verdicts, per the tip in section
3.3).

**Point 3 — Effective R&D (PASS if new-product sales per R&D dollar beat the
industry median).**
FY2025 sales of products launched since 2023-01-01, divided by total R&D spent
in 2023–2025, compared with the industry-median `new_product_sales_per_rd`.
Fisher's point is that R&D should *produce* sellable products: "the results of
research must show in the income statement." A company whose recent products
generate more sales per R&D dollar than its industry's median clears the bar;
one whose R&D converts poorly fails. Evidence: `orders` joined with
`products.launch_date`, `monthly_costs.research_development`,
`industry_medians.new_product_sales_per_rd`.

**Point 5 — Worthwhile profit margin (PASS if FY2025 operating margin is at or
above the industry median).**
Operating margin = (revenue − cost of sales − selling & admin − R&D) ÷ revenue
for FY2025, compared with `industry_medians.operating_margin_pct`. Fisher
wants margins that are "high enough, in comparison with the company's
competitors, to make the margin worthwhile." Beating the industry's median
operating margin is exactly that comparison. Evidence: `orders` (revenue),
`monthly_costs` (all three cost lines), `industry_medians.operating_margin_pct`.

**Point 13 — Growth without dilutive financing (PASS if cash plus 12 quarters
of operating cash flow covers planned capex).**
Cash at the end of 2026Q2 plus operating cash flow of the most recent 12
quarters, versus total planned capex for 2026–2028 in `capex_plan`. Fisher's
fear is that fast growth forces "the issuance of additional stock, largely
cancelling the benefit of the anticipated growth." If the company can fund its
planned investment from the cash on hand and what the business itself
generates, no dilution is needed and it passes; if the plan exceeds that
funding, it will have to raise equity and it fails. Evidence:
`quarterly_cash.cash_end` and `operating_cash_flow`, `capex_plan`.

### Design

```
                    ┌────────────────────────────────────────────┐
                    │   build_agent() → ChatDeepSeek (v4-flash)  │
                    │   (temperature 0, DeepSeek API key from .env) │
                    └───────────────▲────────────────────────────┘
                                    │ writes per-company summary
┌───────────────────────────┐      │
│ analyze_companies()       │──────┘
│ per company (parallel):   │
│                           │
│  ┌─────────────────────┐  │   ┌──────────────────────────────┐
│  │ tools[2] sql_query  │──┼──▶│ 1. np_per_rd (FY2025 sales of │
│  └─────────────────────┘  │   │    products launched ≥2023 ÷  │
│                           │   │    R&D 2023–2025)            │
│  six SQL statements,      │   │ 2. opm (FY2025 revenue minus  │
│  computed by SQL not      │   │    COGS/SGA/R&D, in %)        │
│  by the model             │   │ 3. cash + 12-quarter OCF      │
│                           │   │ 4. industry medians (per-RD,  │
│                           │   │    operating margin)          │
│                           │   │ 5. planned capex 2026–2028    │
│                           │   └──────────┬───────────────────┘
│                           │              ▼
│  deterministic verdicts   │   point 3: np_per_rd > median → PASS
│  points = {3,5,13}        │   point 5: opm ≥ median → PASS
│                           │   point 13: cash+OCF > capex → PASS
└───────────────────────────┘
```

Each company gets the four tools (`list_documents`, `read_document`,
`sql_query`, `interview`) built by the provided runner. `analyze_companies`
runs the companies in parallel with `asyncio.gather`. For every company it
issues six SQL statements through the `sql_query` tool — never touching
`company.db` directly and never doing arithmetic in the model's head — and
compares each result with the company's own industry median (or its planned
capex) to produce a deterministic PASS/FAIL for the three chosen points. The
DeepSeek model is then called once per company to write the two-to-three
sentence analyst-style summary explaining the verdicts, which lands in the
`summary` column of `results.csv`. Any per-company exception (e.g. an API
failure) is caught so the company still gets an entry and the run never
crashes.

### Results

On `public_test` (20 companies, 3 points each = 60 verdicts), the agent scores
**60/60 correct, balanced point accuracy 100.0%**, i.e. both the true-PASS
share and the true-FAIL share are 100%. With `CHOSEN_POINTS = [3, 5, 13]` the
printed score was:

```
Processed 20 companies. Wrote results.csv. Your points: 3, 5, 13.
Point accuracy: 60/60 (balanced: 100.0%).
```

The result was reproduced across three runs (grading takes the average of
three). **There is no disagreement with the public answers** — the rules above
match the answer key for every one of the 20 public companies, including all
six FAIL cases per point (everline, falcrest, halcyon, ironbark, lindale,
northwind on point 5; aurel, driftwood, dunmore, halcyon, ironbark, lindale on
point 3; bramble, elmstead, emberly, granite, juniper, halcyon on point 13).
The margin between each company's computed value and the rule line is
comfortably large in every case (e.g. new-product sales per R&D dollar ranges
from 0.87 to 2.62 against industry medians of 0.79 to 2.06), so the verdicts
are stable and the same rules should transfer to the private set, which uses
the same answer key rules.
