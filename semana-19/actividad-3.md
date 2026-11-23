# Week 19, activity 3: foundation (network, keys, endpoints, inventory)

**Closed.** The one criterion left open here was closed later by live evidence (see the end).

Verified:
- Every encryptable resource points at the project key, and no inbound rule admits internet or an open CIDR (tests in
  `semana-19/tests/test_infra_cdk.py`).
- Deploy and teardown timings are recorded in `semana-19/resultados/tiempos_despliegue.jsonl`.
- The final inventory reports `"quedan": "nada"` with nothing unexpected.
- The DNS configuration of the interface endpoints: one subnet each, in `us-east-1a`, with private DNS enabled and the
  private hosted zones associated with the VPC.

Open: resolution of the endpoint names from inside the VPC was not verified live. The base stack's default
security group custom resource needs `ec2:AuthorizeSecurityGroupIngress`, which the permissions boundary
(`semana19-limite`) does not allow, so the base stack failed to create and the probe could not run. Closing this needs
a boundary change in the control stack. It was left open on purpose: the configuration is verified, and widening the
boundary for one check was not worth it.

The opt-in DNS probe (`cdk deploy -c sonda=1`) stays in the base stack for when the boundary is fixed.

**Closed later, by the activity 8 run (2026-11-19).** The tools Lambda runs in the VPC's isolated subnets, which have
no route to the internet (`resultados/seguridad/verificacion.json`, check `red`). In the approval test it called
Step Functions `StartExecution`, and the execution started (`resultados/eval_aws/aprobacion_e2e.json`, step 0 and the
execution history). Step Functions is reachable from those subnets only through the interface endpoint, so the
service's regional name resolved to the endpoint through its private DNS. The datos loader did the same with Secrets
Manager in activity 4. The opt-in probe was not needed.
