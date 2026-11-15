"""Week 12, activity 10: summarizes `aws ce get-cost-and-usage` (DAILY, grouped by SERVICE and RECORD_TYPE).

The week's cost is the GROSS USAGE (RECORD_TYPE = Usage): if the account has promotional credits, they appear
as negative Credit records, and the net can come out at $0 even though there was consumption.
"""
import collections
import json
import sys

SEMANA = ("Bedrock", "Claude", "Cohere", "S3", "Simple Storage", "Data Automation")
d = json.load(sys.stdin)
uso, tipo, dia = collections.defaultdict(float), collections.defaultdict(float), collections.defaultdict(float)
for r in d["ResultsByTime"]:
    for g in r["Groups"]:
        servicio, registro = g["Keys"]
        c = float(g["Metrics"]["UnblendedCost"]["Amount"])
        tipo[registro] += c
        if registro == "Usage":
            uso[servicio] += c
            dia[r["TimePeriod"]["Start"]] += c
print("Gross usage per service (before credits)\n\n| Service | USD | Week 12 |\n|---|---|---|")
tot = sem = 0.0
for s, c in sorted(uso.items(), key=lambda x: -x[1]):
    if abs(c) < 1e-6:
        continue
    es = any(k in s for k in SEMANA)
    tot += c
    sem += c if es else 0
    print(f"| {s} | {c:.4f} | {'sí' if es else 'no'} |")
print(f"| **Gross usage of the account** | **{tot:.4f}** | |")
print(f"| **Gross usage of week 12 services** | **{sem:.4f}** | |\n")
print("Net by record type\n\n| Type | USD |\n|---|---|")
for k, c in sorted(tipo.items()):
    print(f"| {k} | {c:.4f} |")
print(f"| **Net payable** | **{sum(tipo.values()):.4f}** |\n")
print("| Day | Gross usage USD |\n|---|---|")
for k in sorted(dia):
    print(f"| {k} | {dia[k]:.4f} |")
print("\nEstimated data (not yet consolidated):", "sí" if any(r.get("Estimated") for r in d["ResultsByTime"]) else "no")
