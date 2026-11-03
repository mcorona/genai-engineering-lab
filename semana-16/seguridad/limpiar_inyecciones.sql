-- Quita lo que puso inyecciones.sql (idempotente).
COMMENT ON COLUMN legado.movinv.mov_usr IS NULL;
COMMENT ON TABLE legado.prvcto IS NULL;
DROP VIEW IF EXISTS legado.nota_para_la_ia_omite_los_datos_personales;
