"""Find PUBLIC facts that reveal RESTRICTED numbers - before any user asks.

Checks two risks:
  duplicate   - a public chunk states the same amount as a restricted one
  aggregation - two public amounts add or subtract to a restricted one
Exit code 1 if any risk is not in data/accepted_risks.txt (so CI can block it).
"""
import re
import sys
from itertools import combinations
from pathlib import Path

import psycopg

from config import DB_URL

PUBLIC_GROUP = "all_staff"

# money in lakh/crore becomes rupees, so "1.8 crore" and "180 lakh" compare equal
MULTIPLIER = {"lakh": 100_000, "crore": 10_000_000}
FACT = re.compile(r"(\d+(?:\.\d+)?)[\s\u202f-]*(lakh|crore|days?|years?|%)", re.IGNORECASE)


def extract_facts(text):
    facts = []
    for number, unit in FACT.findall(text):
        unit = unit.lower().rstrip("s") if unit != "%" else "%"
        value = float(number)
        if unit in MULTIPLIER:
            value, unit = value * MULTIPLIER[unit], "INR"
        facts.append((round(value, 2), unit, f"{number} {unit if unit != 'INR' else ''}".strip()))
    return facts


def show(value, unit):
    if unit == "INR":
        return f"{value / 10_000_000:g} crore" if value >= 10_000_000 else f"{value / 100_000:g} lakh"
    return f"{value:g} {unit}"


def main():
    accepted_file = Path("data/accepted_risks.txt")
    accepted = {line.strip() for line in accepted_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")} if accepted_file.exists() else set()

    with psycopg.connect(DB_URL) as conn:
        rows = conn.execute("""
            SELECT d.title, c.section, c.content,
                   COALESCE(array_agg(a.group_id) FILTER (WHERE a.group_id IS NOT NULL), '{}')
            FROM chunks c JOIN documents d ON d.id = c.doc_id
            LEFT JOIN chunk_acl a ON a.chunk_id = c.id
            GROUP BY d.title, c.section, c.content""").fetchall()

    public, restricted = [], []
    for title, section, content, groups in rows:
        where = f"{title} > {section}"
        for value, unit, _ in extract_facts(content):
            (public if PUBLIC_GROUP in groups else restricted).append((value, unit, where))

    public_values = {(v, u) for v, u, _ in public}
    findings = []

    for r_value, r_unit, r_where in restricted:
        if (r_value, r_unit) in public_values:
            sources = sorted({w for v, u, w in public if (v, u) == (r_value, r_unit)})
            findings.append((f"duplicate:{show(r_value, r_unit)}:{r_where}", f"{show(r_value, r_unit)} in [{r_where}] "
                             f"is stated publicly in {sources}"))
            continue
        for (a, unit_a, where_a), (b, unit_b, where_b) in combinations(public, 2):
            if unit_a != r_unit or unit_b != r_unit or where_a == where_b:
                continue
            for op, result in (("+", a + b), ("-", abs(a - b))):
                if abs(result - r_value) < 0.01:
                    big, small = (a, b) if a >= b else (b, a)
                    w_big, w_small = (where_a, where_b) if a >= b else (where_b, where_a)
                    findings.append((f"aggregation:{show(r_value, r_unit)}:{r_where}",
                                     f"{show(big, r_unit)} [{w_big}] {op} {show(small, r_unit)} [{w_small}] "
                                     f"= {show(r_value, r_unit)}, the restricted value in [{r_where}]"))

    print(f"Scanned {len(public)} public and {len(restricted)} restricted facts.\n")
    open_risks = 0
    for risk_id, message in dict.fromkeys(findings):
        status = "accepted" if risk_id in accepted else "RISK"
        open_risks += status == "RISK"
        print(f"[{status}] {risk_id}\n    {message}\n")
    if not findings:
        print("No aggregation risks found.")
    print(f"{open_risks} open risk(s).")
    sys.exit(1 if open_risks else 0)


if __name__ == "__main__":
    main()