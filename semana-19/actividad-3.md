# Week 19, activity 3: foundation (network, keys, endpoints, inventory)

**Closed, with one criterion open.**

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
