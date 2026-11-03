"""Week 17, activity 3: LegacyBridge instrumented end to end with OpenTelemetry GenAI.

    esquema            the locked span shape (allowed attributes, validators, keyed hashes)
    trazas_agente      invoke_agent / chat / execute_tool around the week 13 loop
    trazas_cliente     the week 14 MCP client keeps the agent's trace context across its thread hand-off
    trazas_servidor    authorize / handle_tool / SELECT spans on the week 14 server, continuing the same trace
    modelo_guionado    a scripted model ($0) to run the whole stack without the API
"""
