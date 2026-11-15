-- Week 14, activity 5: one PostgreSQL role per scope profile (idempotent; run as an administrator).
-- The MCP server connects as copilot_nlq and, in each transaction, runs SET LOCAL ROLE to the token profile's role:
-- the database is the last line of defense even if the guard failed. The FKs count: art_prv (supplier) and art_cst (cost)
-- are read only by legado_r_proveedores.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['legado_r_leer', 'legado_r_ventas', 'legado_r_proveedores',
                           'legado_perfil_l', 'legado_perfil_lv', 'legado_perfil_lp', 'legado_perfil_lvp'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT', r);
    END IF;
  END LOOP;
END $$;

-- start from scratch on each run (this also revokes the column privileges)
REVOKE ALL ON ALL TABLES IN SCHEMA legado FROM legado_r_leer, legado_r_ventas, legado_r_proveedores;
REVOKE ALL ON SCHEMA legado FROM legado_r_leer, legado_r_ventas, legado_r_proveedores;

GRANT USAGE ON SCHEMA legado TO legado_r_leer, legado_r_ventas, legado_r_proveedores;
GRANT SELECT ON legado.almmst, legado.exidet, legado.artnot TO legado_r_leer;
GRANT SELECT (art_cd, art_dsc, art_lin, art_ptr, art_crt) ON legado.artmst TO legado_r_leer;
GRANT SELECT ON legado.vtadia TO legado_r_ventas;
GRANT SELECT ON legado.prvmst, legado.ocpcab, legado.artmst TO legado_r_proveedores;

GRANT legado_r_leer TO legado_perfil_l, legado_perfil_lv, legado_perfil_lp, legado_perfil_lvp;
GRANT legado_r_ventas TO legado_perfil_lv, legado_perfil_lvp;
GRANT legado_r_proveedores TO legado_perfil_lp, legado_perfil_lvp;

-- the connection role can only switch to these profiles (NOINHERIT: it does not gain their privileges by itself)
GRANT legado_perfil_l, legado_perfil_lv, legado_perfil_lp, legado_perfil_lvp TO copilot_nlq;
