# Week 19, activity 4: cost plan (estimate, before any resource exists)

Status: **estimate only.** Nothing is created in AWS by this document. Manuel authorizes it before `--si`.
Prices: AWS Price List API, us-east-1, on-demand, read on 2026-11-14. Each price shows its catalog SKU.
Codes: D = measured in the account, M = not measured (never used here), N = no price found in the Price List API.

## Per-hour cost while the database is up

| Item | Price | Source (SKU) | Per hour |
|---|---|---|---|
| RDS PostgreSQL db.t4g.micro, Single-AZ | 0.016 USD/h | AmazonRDS `9HPEGXQTDDGH53C9` | 0.016000 |
| RDS gp3 storage, 20 GB (smallest allocation, assumption) | 0.115 USD/GB-mo | AmazonRDS `2XPS3A47BS2PYAZE` (deployment option not confirmed; see note) | 0.003151 (0.115 × 20 ÷ 730) |
| Secrets Manager, 1 secret (master password, generated) | 0.40 USD/secret-mo | AWSSecretsManager `BJ3PQ9BYGU6P632F` | 0.000548 (0.40 ÷ 730) |
| VPC interface endpoint, Secrets Manager (one AZ, one ENI) | 0.01 USD/h | AmazonVPC `EN2N5TATXE673A3B` (PrivateLink, us-east-1) | 0.010000 |
| **Total while up** | | | **0.029699** |

Note on the storage SKU: three SKUs carry the same 0.115 price for `RDS:GP3-Storage`; the Single-AZ one is not confirmed.
The difference is zero at this price, so the estimate does not change, but the SKU is not verified as Single-AZ.

## One-shot loader (Lambda in the VPC)

| Item | Price | Source (SKU) | Estimate |
|---|---|---|---|
| Duration, 512 MB × 60 s = 30 GB-s | 0.0000166667 USD/GB-s | AWSLambda `TG3M4CAGBA3NYQBH` (x86 standard) | 0.000500 |
| Requests, 1 invocation | 0.0000002 USD/req | AWSLambda `GU2ZS9HVP6QTQ7KE` | 0.000000 |
| **Loader, one run** | | | **0.000500** |

## Not priced

| Item | Status | Why |
|---|---|---|
| Titan Text Embeddings V2 | **N** | Not found in `AmazonBedrockFoundationModels` or `AmazonBedrockService` (checked 2026-11-14) |
| S3 Vectors store | **N** | No Price List service code for S3 Vectors in us-east-1 |
| Encrypted S3 bucket for the dictionary | not counted | Under 1 MB of text; storage cost is below the cent |
| KMS requests | not counted | Under 1,000 calls per session |
| Data transfer | not counted | In-VPC traffic only |

## Scenarios

| Scenario | Hours up | RDS + storage | Loader | Total (priced items only) |
|---|---|---|---|---|
| Planned (loader, checks, teardown in the same session) | 2 | 0.059398 (RDS + storage 0.039398; endpoint 0.020000) | 0.000500 | **0.0599 USD** |
| Left up by mistake for 24 h | 24 | 0.712776 (RDS + storage 0.472776; endpoint 0.240000) | 0.000500 | 0.7133 USD |

The second scenario is the cost of forgetting the teardown. It stays under the USD 5/week cap.

Only the Secrets Manager endpoint is in the stack: the Bedrock Agent endpoint was removed (its private DNS conflicted in the VPC).

Not counted: PrivateLink data processing (USD per GB on the endpoints). Only a few KB pass through them per session, so it rounds below one thousandth of a dollar.

## Decisions taken

- **Storage:** 20 GB gp3, the smallest allocation. No final snapshot at teardown, so no snapshot storage cost remains.
- **Backups:** automated backups at the minimum retention. Backup storage up to the allocated size is free.
- **Deletion protection:** off in the lab only; documented in `base.md` as the plan requires.
- **Teardown:** the database is deleted by `destruir.sh` in the same session as the deployment, after the tests.

## Authorization

Manuel's OK is needed before any `--si` for activity 4. Estimated cost: **≈ 0.06 USD** for a planned session; ≈ 0.71 USD if left up 24 h. Both are far below the USD 5/week cap, so they count as approved under the rule Manuel set on 2026-11-14.
