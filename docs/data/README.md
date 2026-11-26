# Data guides

[Glossary](../glossary.md) · [Root README](../../README.md)

The lab's evaluation data is in Spanish, and so are many recorded results. Neither is translated: translating a
corpus or a gold set would change what was measured, and editing a recorded output would falsify it. Each data or
results folder has an English `README.md` that says what its files are, which script writes or reads them, and what
their Spanish keys mean.

Some files sit outside those folders: loose files in a week folder, and folders that cannot hold a README because
code reads, hashes, packages or deploys every file in them (the corpora, the week 12 ingestion package, the week 16
plugin, the week 19 loader). The guides below describe them, one per week. They live here, not in the week folders, because the paid eval workflows
run on any change in a week folder except a `README.md`.

`docs/tests/test_data_readmes.py` checks that every Spanish data file and every recorded result is described, that
every file pattern matches a file, and that every key listed exists in the files.

| Week folder | Guide |
|---|---|
| [`semana-01/`](../../semana-01/) | [Week 1 data and loss logs (recorded evidence)](semana-01.md) |
| [`semana-02/`](../../semana-02/) | [Week 2 data and results (recorded evidence)](semana-02.md) |
| [`semana-03/`](../../semana-03/) | [Week 3 business rules (Spanish data)](semana-03.md) |
| [`semana-04/`](../../semana-04/) | [Week 4 benchmark queries (Spanish data)](semana-04.md) |
| [`semana-07/`](../../semana-07/) | [Week 7 schemas (Spanish data)](semana-07.md) |
| [`semana-08/`](../../semana-08/) | [Week 8 corpus (Spanish data)](semana-08.md) |
| [`semana-09/`](../../semana-09/) | [Week 9 tenant beta corpus (Spanish data)](semana-09.md) |
| [`semana-10/`](../../semana-10/) | [Week 10 source documents (Spanish data)](semana-10.md) |
| [`semana-12/`](../../semana-12/) | [Week 12 ingestion package (recorded evidence)](semana-12.md) |
| [`semana-13/`](../../semana-13/) | [Week 13 data outside the gold set and results folders (Spanish data)](semana-13.md) |
| [`semana-14/`](../../semana-14/) | [Week 14 data outside the results folder (Spanish data)](semana-14.md) |
| [`semana-16/`](../../semana-16/) | [Week 16 data and evidence outside the data folders (Spanish data)](semana-16.md) |
| [`semana-18/`](../../semana-18/) | [Week 18 data (Spanish data)](semana-18.md) |
| [`semana-19/`](../../semana-19/) | [Week 19 data (Spanish data and recorded evidence)](semana-19.md) |
