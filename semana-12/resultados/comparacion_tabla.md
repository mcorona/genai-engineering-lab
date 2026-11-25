| Option | Ingestion mode | Generator | Lang | recall@5 | nDCG@10 | faithfulness | answer relevancy | Correctness | Correct abstention | Leakage (chunks / queries) | Latency p50 / p95 (s) | USD per query |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| In-house pipeline (pgvector + Haiku reranking) | in-house chunks | common | ES | 1.000 | 0.962 | 0.849 | 0.879 | 1.000 | 10/10 | 0 (weeks 9-10) | 3.89 / 6.07 | 0.00070 |
| In-house pipeline (pgvector + Haiku reranking) | in-house chunks | common | EN | 1.000 | 0.965 | 0.830 | 0.866 | 1.000 | 10/10 | 0 (weeks 9-10) | 3.89 / 6.07 | 0.00070 |
| Bedrock KB, Retrieve | managed: default chunking/parser | common | ES | 0.823 | 0.775 | 0.815 | 0.750 | 0.815 | 10/10 | 0 / 96 | ret. 0.5* | 0.00035 |
| Bedrock KB, Retrieve | managed: default chunking/parser | common | EN | 0.823 | 0.770 | 0.881 | 0.766 | 0.815 | 10/10 | 0 / 96 | ret. 0.5* | 0.00035 |
| Bedrock KB, Retrieve | managed: fixed 100 tok / 20% | common | ES | 0.815 | 0.752 | 0.888 | 0.761 | 0.831 | 10/10 | 0 / 96 | ret. 0.49* | 0.00028 |
| Bedrock KB, Retrieve | managed: fixed 100 tok / 20% | common | EN | 0.831 | 0.756 | 0.828 | 0.780 | 0.831 | 10/10 | 0 / 96 | ret. 0.49* | 0.00028 |
| Bedrock KB, Retrieve | managed: fixed + BDA multimodal | common | ES | 0.739 | 0.681 | 0.761 | 0.694 | 0.708 | 10/10 | 0 / 96 | ret. 0.98* | 0.00027 |
| Bedrock KB, Retrieve | managed: fixed + BDA multimodal | common | EN | 0.739 | 0.685 | 0.731 | 0.679 | 0.739 | 10/10 | 0 / 96 | ret. 0.98* | 0.00027 |
| Bedrock KB, Retrieve | controlled: in-house chunks | common | ES | 1.000 | 0.898 | 0.881 | 0.870 | 0.985 | 10/10 | 0 / 96 | 2.58 / 4.09 | 0.00027 |
| Bedrock KB, Retrieve | controlled: in-house chunks | common | EN | 1.000 | 0.901 | 0.847 | 0.874 | 0.985 | 10/10 | 0 / 96 | 2.58 / 4.09 | 0.00027 |
| Bedrock RetrieveAndGenerate | managed: default chunking/parser | Haiku 4.5 (Bedrock) | ES | 0.823 | 0.775 | 0.938 | 0.749 | 0.815 | 10/10 | same filter as Retrieve | ret. 0.5* | 0.00172 (est.) |
| Bedrock RetrieveAndGenerate | managed: default chunking/parser | Haiku 4.5 (Bedrock) | EN | 0.823 | 0.770 | 0.801 | 0.742 | 0.815 | 10/10 | same filter as Retrieve | ret. 0.5* | 0.00172 (est.) |
| Bedrock RetrieveAndGenerate | managed: fixed + BDA multimodal | Haiku 4.5 (Bedrock) | ES | 0.739 | 0.681 | 0.739 | 0.899 | 0.969 | 10/10 | 0 / 96 | 1.5 / 2.21 | 0.00108 (est.) |
| Bedrock RetrieveAndGenerate | managed: fixed + BDA multimodal | Haiku 4.5 (Bedrock) | EN | 0.739 | 0.685 | 0.735 | 0.900 | 0.969 | 10/10 | 0 / 96 | 1.5 / 2.21 | 0.00108 (est.) |
| Bedrock RetrieveAndGenerate | controlled: in-house chunks | Haiku 4.5 (Bedrock) | ES | 1.000 | 0.898 | 0.947 | 0.918 | 0.985 | 10/10 | same filter as Retrieve | ret. 0.5* | 0.00117 (est.) |
| Bedrock RetrieveAndGenerate | controlled: in-house chunks | Haiku 4.5 (Bedrock) | EN | 1.000 | 0.901 | 0.942 | 0.907 | 0.985 | 10/10 | same filter as Retrieve | ret. 0.5* | 0.00117 (est.) |
| Vertex AI Search, hybrid | managed: layout parser | common | ES | 0.831 | 0.816 | 0.871 | 0.807 | 0.923 | 10/10 | 0 / 96 | ret. 0.43* | 0.00034 + search past 10k/mo |
| Vertex AI Search, hybrid | managed: layout parser | common | EN | 0.823 | 0.795 | 0.861 | 0.807 | 0.923 | 10/10 | 0 / 96 | ret. 0.43* | 0.00034 + search past 10k/mo |
| Vertex AI Search, vector | managed: layout parser | common | ES | 0.808 | 0.787 | 0.867 | 0.794 | 0.908 | 10/10 | 0 / 96 | ret. 0.41* | 0.00032 + search past 10k/mo |
| Vertex AI Search, vector | managed: layout parser | common | EN | 0.808 | 0.787 | 0.863 | 0.801 | 0.908 | 10/10 | 0 / 96 | ret. 0.41* | 0.00032 + search past 10k/mo |
| Vertex AI Search, semantic ranker | managed: layout parser | common | ES | 0.831 | 0.831 | 0.852 | 0.802 | 0.923 | 10/10 | 0 / 96 | 2.48 / 3.84 | 0.00132 + search past 10k/mo |
| Vertex AI Search, semantic ranker | managed: layout parser | common | EN | 0.831 | 0.825 | 0.854 | 0.813 | 0.923 | 10/10 | 0 / 96 | 2.48 / 3.84 | 0.00132 + search past 10k/mo |
| Vertex AI Search, hybrid | controlled: in-house chunks | common | ES | 1.000 | 0.958 | 0.860 | 0.882 | 1.000 | 10/10 | 0 / 96 | ret. 0.39* | 0.00021 + search past 10k/mo |
| Vertex AI Search, hybrid | controlled: in-house chunks | common | EN | 0.962 | 0.889 | 0.859 | 0.889 | 0.969 | 10/10 | 0 / 96 | ret. 0.39* | 0.00021 + search past 10k/mo |
| Vertex AI Search, vector | controlled: in-house chunks | common | ES | 1.000 | 0.923 | 0.844 | 0.881 | 1.000 | 10/10 | 0 / 96 | ret. 0.38* | 0.00021 + search past 10k/mo |
| Vertex AI Search, vector | controlled: in-house chunks | common | EN | 1.000 | 0.910 | 0.869 | 0.890 | 0.985 | 10/10 | 0 / 96 | ret. 0.38* | 0.00021 + search past 10k/mo |
| Vertex AI Search, semantic ranker | controlled: in-house chunks | common | ES | 1.000 | 0.983 | 0.790 | 0.890 | 0.985 | 10/10 | 0 / 96 | 2.4 / 3.94 | 0.00121 + search past 10k/mo |
| Vertex AI Search, semantic ranker | controlled: in-house chunks | common | EN | 1.000 | 0.971 | 0.814 | 0.879 | 0.985 | 10/10 | 0 / 96 | 2.4 / 3.94 | 0.00121 + search past 10k/mo |
