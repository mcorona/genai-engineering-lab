# Week 19, activity 4: data (RDS, legacy schema, Knowledge Base)

**Deletion protection is off in the lab, on purpose.** The `semana19-datos` RDS instance is created with
`deletion_protection=False` and `RemovalPolicy.DESTROY`, and backups are kept for one day, so the teardown can remove it
completely and leave nothing billed. A production deployment would turn deletion protection on, use the 2-AZ layout and
longer backup retention, and keep the removal policy at retain; none of that is in the lab (see `Fas5Sema19.md`,
"lab" versus "prod").

**The Knowledge Base ingestion job is started by API, not declared in IaC.** CloudFormation has no resource for a
Bedrock ingestion job, and the `bedrock-agent` endpoint has no VPC-private DNS name that works here (AWS rejected it in
the VPC), so the loader only uploads the data dictionary documents to the bucket and `desplegar.sh` (step 5) calls
`aws bedrock-agent start-ingestion-job` from the operator's terminal. The Lambda role is allowed `bedrock:StartIngestionJob`
for that case. This is a documented deviation from "everything declared in IaC".
