// Week 19, activity 7: the read tools. Any caller whose access token carries the scope legado/leer: the analysts,
// the buyers and the three approval groups (computo/tokens.py, GRUPOS_A_SCOPES). The scope claim is one string of
// space-separated values, so the match includes the delimiters: "legado/leerX" does not pass.
permit(
  principal is AgentCore::OAuthUser,
  action in [AgentCore::Action::"herramientas___describir_esquema", AgentCore::Action::"herramientas___ejecutar_sql"],
  resource == AgentCore::Gateway::"{{GATEWAY_ARN}}"
)
when {
  principal.hasTag("scope") &&
  (principal.getTag("scope") == "legado/leer" ||
   principal.getTag("scope") like "legado/leer *" ||
   principal.getTag("scope") like "* legado/leer" ||
   principal.getTag("scope") like "* legado/leer *")
};
