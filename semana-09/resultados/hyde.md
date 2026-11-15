# Activity 3: HyDE with claude-haiku-5-5

The week 8 vector search (bge-m3, `semana8` index, fixed 400/80). Script: `experimentos/hyde.py`.
Haiku writes a hypothetical passage; that passage is embedded and searched instead of the original question.
Base: a self-contained question. Follow-up: the passage is generated with the previous question as context.
Permissions are outside this metric (they are evaluated in activity 5).

## Valid run (max_tokens 1500)

Fallback check: 0 of 130 passages equal to the question. Detail: `hyde_detalle.csv`.

| Type | Language | Variant | recall@5 | nDCG@10 | MRR | Cost per query (USD) | HyDE latency p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| base | es | original | 1.000 | 0.904 | 0.874 | - | - |
| base | es | HyDE | 0.960 | 0.886 | 0.856 | 0.000098 | 1375 / 3129 |
| follow-up | es | original | 0.933 | 0.809 | 0.747 | - | - |
| follow-up | es | HyDE | 0.933 | 0.750 | 0.668 | 0.000097 | 1405 / 2688 |
| base | en | original | 1.000 | 0.885 | 0.845 | - | - |
| base | en | HyDE | 0.880 | 0.816 | 0.772 | 0.000137 | 1914 / 3184 |
| follow-up | en | original | 0.867 | 0.802 | 0.739 | - | - |
| follow-up | en | HyDE | 0.933 | 0.774 | 0.702 | 0.000159 | 2165 / 3091 |

## First run (max_tokens 250, discarded as a measurement)

Five of 130 responses had only the reasoning block and no text; the script used the original question as the passage. In addition, most outputs ended close to the limit and were probably truncated. The limit was raised to 1500 and the run repeated. The CSV of that run is kept as `hyde_detalle_corrida1.csv` in the local folder, not in the repository.

## Reading

- **It improves no ranking metric.** nDCG@10 and MRR drop in all four cells.
- **Recall:** base drops in ES (one question fewer) and in EN (six questions fewer). EN follow-ups gain one question; ES follow-ups do not change.
- **Cost:** $0.000097 to $0.000159 per query, up to about twice the cost of query rewriting, because of the longer text output.
- **Latency:** p50 between 1.4 and 2.2 s, with p95 of up to 3.2 s. It is the slowest technique tested so far, and it brings no gain.

The block types confirm what was seen with query rewriting: Haiku returns `thinking` blocks in addition to `text`, and those tokens are billed as output.

## Conclusion

HyDE improves neither recall nor ranking on this gold set. It is documented as a technique that does not help. It is not adopted by default, either for base questions or for follow-ups. The recall difference on EN base questions (six questions) is the clearest signal against it.

## Limitations

- One valid run. The variability of Haiku observed with query rewriting suggests that differences of one or two questions can be noise.
- A single generation model (Haiku) and a single hypothetical-passage length.
- The permission cases are not part of this metric.
