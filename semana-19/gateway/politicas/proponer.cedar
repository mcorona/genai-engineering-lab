// Week 19, activity 7: the protected tool is proponer_orden_compra. The approval is not an agent tool: it is
// POST /aprobaciones/{id} on the HTTP API, decided by a person of the right level with the scope
// legacybridge/aprobaciones (activity 6, PR 244), and it stays there. The agent's only write is the proposal, so
// this is the rule that keeps the separation of duties on the gateway path:
//   - only the buyers propose: the token carries legado/compras_proponer (the approval groups never do);
//   - the requester is the caller: context.input.solicitante must be the token's own sub. The agent Lambda sets
//     it from the verified token; a request that names someone else is denied before the tools Lambda runs.
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"herramientas___proponer_orden_compra",
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") &&
  (principal.getTag("scope") == "legado/compras_proponer" ||
   principal.getTag("scope") like "legado/compras_proponer *" ||
   principal.getTag("scope") like "* legado/compras_proponer" ||
   principal.getTag("scope") like "* legado/compras_proponer *") &&
  principal.hasTag("sub") &&
  context.input.solicitante == principal.getTag("sub")
};
