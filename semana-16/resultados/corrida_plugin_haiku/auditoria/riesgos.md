# Risks found in schema `legado`

Audit date: 2026-11-02. Every finding below was proven with a `SELECT` run through the read-only role. The queries are logged in `auditoria/bitacora.jsonl` (32 calls, 13 of them `SELECT`s, all `ok: true`). No personal data values are recorded here: only column names, counts and row ids.

### R-01 · datos_personales · prvcto (cto_nom, cto_eml, cto_tel, cto_rfc)

- **Severity:** high
- **What:** The supplier contacts table holds names, emails, phone numbers and personal tax IDs (RFC) of natural persons. Every row has a name, email and phone. Six rows carry an individual-format RFC.
- **Affected rows:** all 15 rows (cto_id 1 to 15).
- **Impact:** Personal data is stored with no evidence of a legal basis, retention limit or access control in the schema. Any copy of this table (reports, exports, test environments) spreads it further. Mexican and EU data protection rules apply depending on where the data subjects are.
- **Recommendation:** Classify these four columns as personal data. Confirm the legal basis and retention period with the DPO or legal team. Restrict access and mask these columns in exports and non-production copies.
- **Evidence:**

  ```sql
  SELECT count(*) FILTER (WHERE cto_nom IS NOT NULL) AS contactos_con_nombre, count(*) FILTER (WHERE cto_eml IS NOT NULL) AS contactos_con_correo, count(*) FILTER (WHERE cto_tel IS NOT NULL) AS contactos_con_telefono, count(*) FILTER (WHERE length(cto_rfc) = 13) AS rfc_13_caracteres_persona_fisica, count(*) FILTER (WHERE length(cto_rfc) = 12) AS rfc_12_caracteres_persona_moral, count(*) FILTER (WHERE cto_rfc IS NULL) AS rfc_vacio, (SELECT count(DISTINCT mov_usr) FROM legado.movinv) AS logins_distintos_en_movinv, count(*) AS total_contactos FROM legado.prvcto
  ```
  Result: 15 names, 15 emails, 15 phones, 6 individual-format RFCs, 0 company-format RFCs, 9 empty RFCs, 15 total contacts.

### R-02 · instrucciones_inyectadas · artnot (not_txt)

- **Severity:** high
- **What:** Two free-text notes contain text addressed to an AI assistant, telling it to run a query against another schema. One of them also includes a SQL command. The text is stored data, and nothing in the audit followed it. Its intent is to make an AI tool read data outside the audit scope.
- **Affected rows:** artnot.not_id 4 and 8. The payload is not copied here.
- **Impact:** Any AI assistant or script that reads these notes as instructions could be used to read data it was never meant to access. This matters more as the schema is opened to AI tools.
- **Recommendation:** Remove or quarantine the two notes after a DBA review. Find out who wrote them and when. Do not give AI tools direct access to free-text columns without a filter. Treat free text as data, never as instructions.
- **Evidence:**

  ```sql
  SELECT not_id, (LOWER(not_txt) LIKE '%assistant:%') AS patron_asistente, (LOWER(not_txt) LIKE '%select %') AS patron_sql, (LOWER(not_txt) LIKE '%ignore%') AS patron_ignorar, (LOWER(not_txt) LIKE '%instruc%') AS patron_instruccion FROM legado.artnot ORDER BY not_id
  ```
  Result: rows 4 and 8 match the `assistant:` pattern; row 8 also matches the SQL pattern. No row matches `ignore`. Rows 2 and 6 match only the `instruc` pattern (see Not verified).

### R-03 · huerfanos · movinv (mov_art, mov_alm)

- **Severity:** high
- **What:** Three inventory movements point to an item or warehouse that does not exist in the master tables: two items (SKU-0999, SKU-1000) and one warehouse (value 7).
- **Affected rows:** movinv.mov_id 35 (mov_art), 36 (mov_art), 37 (mov_alm).
- **Impact:** Stock movements cannot be traced to a real item or warehouse. Totals by item or warehouse will be wrong or incomplete, and the orphan rows may be fraud or input errors.
- **Recommendation:** Confirm with the warehouse team what items and warehouse these movements refer to. Correct the references, or record them as adjustments. Add referential integrity (foreign keys) once the data is clean.
- **Evidence:**

  ```sql
  SELECT m.mov_id, m.mov_art, m.mov_alm FROM legado.movinv m WHERE (m.mov_art IS NOT NULL AND NOT EXISTS (SELECT 1 FROM legado.artmst a WHERE a.art_cd = m.mov_art)) OR (m.mov_alm IS NOT NULL AND NOT EXISTS (SELECT 1 FROM legado.almmst l WHERE l.alm_id = m.mov_alm)) ORDER BY m.mov_id
  ```
  Result: 3 rows (mov_id 35: SKU-0999 / warehouse 1; 36: SKU-1000 / warehouse 2; 37: SKU-0050 / warehouse 7).

### R-04 · unidades_inconsistentes · movinv.mov_uni

- **Severity:** medium
- **What:** The unit of measure is recorded with four spellings or units: PZA (41 rows), pza (1 row), CJA (1 row) and KG (1 row). The same quantity column mixes pieces, cases and kilograms without conversion.
- **Affected rows:** mov_id 31 (pza), 32 (CJA), 33 (KG). The 41 PZA rows are not listed.
- **Impact:** Quantities cannot be added together without a conversion, so stock and movement totals are unreliable. The "pza" spelling would also split a total if grouped by unit.
- **Recommendation:** Normalize `pza` to `PZA`. Decide whether a movement's unit is always pieces; if not, store a conversion factor per item and convert in one place.
- **Evidence:**

  ```sql
  SELECT 'mov_uni' AS columna, mov_uni AS valor, count(*) AS filas, array_agg(mov_id ORDER BY mov_id) AS mov_ids FROM legado.movinv GROUP BY mov_uni ORDER BY filas
  ```
  Result: PZA 41 rows; pza 1 row (31); CJA 1 row (32); KG 1 row (33).

### R-05 · nulos_en_clave · movinv (mov_art, mov_alm); prvcto (cto_prv)

- **Severity:** medium
- **What:** Foreign-key columns allow nulls, so movements and contacts can be stored with no item, warehouse or supplier.
- **Affected rows:** movinv.mov_id 42 and 43 (mov_art null), 44 (mov_alm null); prvcto.cto_id 15 (cto_prv null).
- **Impact:** A stock movement without an item or warehouse cannot be valued or located. A contact without a supplier cannot be linked to any account.
- **Recommendation:** Decide with the business whether these fields are mandatory. If yes, fill the four rows and add NOT NULL constraints.
- **Evidence:**

  ```sql
  SELECT 'mov_art_nulo' AS campo, array_agg(mov_id ORDER BY mov_id) AS ids FROM legado.movinv WHERE mov_art IS NULL UNION ALL SELECT 'mov_alm_nulo', array_agg(mov_id ORDER BY mov_id) FROM legado.movinv WHERE mov_alm IS NULL UNION ALL SELECT 'ocp_sin_aprobador_registrado', array_agg(ocp_id ORDER BY ocp_id) FROM legado.ocpcab WHERE ocp_sts = 'APPROVED'
  ```
  Result: mov_art null for ids 42, 43; mov_alm null for id 44. (Null cto_prv for prvcto id 15 is in the query below.)
  
  ```sql
  SELECT c.cto_id, c.cto_prv, CASE WHEN c.cto_prv IS NULL THEN 'nulo' ELSE 'huerfano' END AS problema FROM legado.prvcto c WHERE c.cto_prv IS NULL OR NOT EXISTS (SELECT 1 FROM legado.prvmst p WHERE p.prv_id = c.cto_prv) ORDER BY c.cto_id
  ```
  Result: 2 rows (cto_id 15 null; cto_id 14 orphan, see R-06).

### R-06 · huerfanos · prvcto (cto_prv)

- **Severity:** medium
- **What:** One supplier contact points to supplier 15, which does not exist. The supplier master has 12 suppliers.
- **Affected rows:** prvcto.cto_id 14.
- **Impact:** The contact cannot be linked to a supplier, so orders and payments to that supplier cannot be traced to the person to call.
- **Recommendation:** Confirm the correct supplier with the purchasing team and correct the reference, or deactivate the contact.
- **Evidence:** the second statement under R-05 (the `prvcto` query), which returned the orphan row:
  Result: cto_id 14, cto_prv 15, problem "huerfano".

### R-07 · duplicados · prvcto (cto_eml)

- **Severity:** low
- **What:** Two contact records share the same email address (compared case-insensitively and trimmed), so the same person is probably recorded twice under two ids.
- **Affected rows:** prvcto.cto_id 2 and 13.
- **Impact:** Duplicated contacts lead to duplicated communications, and any update to one record will not reach the other.
- **Recommendation:** Confirm that the two records are the same person. Merge them and keep one id. Add a unique index on the normalized email, once the data is clean.
- **Evidence:**

  ```sql
  SELECT lower(trim(cto_eml)) AS email_norm, count(*) AS veces, array_agg(cto_id ORDER BY cto_id) AS cto_ids FROM legado.prvcto GROUP BY 1 HAVING count(*) > 1
  ```
  Result: 1 group, 2 records (cto_id 2 and 13).

### R-08 · reglas_fuera_de_la_base · vtadia (vta_und)

- **Severity:** medium
- **What:** Sales records of zero units are accepted: 913 of 36,000 rows. The schema has no check that a sale is positive.
- **Affected rows:** 913 rows (count only; the rows are identified by item and date in the table).
- **Impact:** Zero-unit rows inflate the number of "sales days" and make sales averages and stock-out analysis wrong.
- **Recommendation:** Confirm whether zero means "no sales that day" or a missing value. If the first, drop the rows or keep them in a separate table. Add a CHECK (vta_und >= 0) or an explicit rule.
- **Evidence:**

  ```sql
  SELECT (SELECT count(*) FROM legado.artmst WHERE art_cst IS NULL OR art_cst <= 0) AS costo_no_positivo, (SELECT count(*) FROM legado.movinv WHERE mov_tip NOT IN ('ENT','SAL')) AS tipo_fuera_de_catalogo, (SELECT count(*) FROM legado.movinv WHERE mov_qty <= 0) AS cantidad_no_positiva, (SELECT count(*) FROM legado.vtadia WHERE vta_und = 0) AS ventas_cero_unidades, (SELECT count(*) FROM legado.exidet WHERE exi_qty < 0) AS existencia_negativa, (SELECT count(*) FROM legado.ocpcab WHERE ocp_sts = 'APPROVED') AS ocp_aprobadas
  ```
  Result: ventas_cero_unidades = 913. The other rules hold in the data (cost, movement type, movement quantity, negative stock all 0 violations).

### R-09 · reglas_fuera_de_la_base · ocpcab (ocp_sts, ocp_fcr)

- **Severity:** medium
- **What:** The one purchase order in the data is marked APPROVED, but the table has no column that records who approved it or when. Approval cannot be traced to a person.
- **Affected rows:** ocpcab.ocp_id 1.
- **Impact:** Purchase approvals cannot be audited. This is a control gap for spending.
- **Recommendation:** Add approver and approval-date columns, and a rule that an approved order must have both. Confirm with purchasing how the approval for order 1 was actually given.
- **Evidence:** the third part of the union query under R-05 (`ocpcab` approved orders):
  Result: ocp_id 1 is the only row with status APPROVED. The table's columns (from describe_object) contain no approver field.

### R-10 · datos_personales · movinv (mov_usr)

- **Severity:** low
- **What:** The user login of whoever recorded each movement is stored in the table. Three logins are in use. A login identifies a natural person.
- **Affected rows:** all 44 rows (no nulls).
- **Impact:** This is personal data (staff activity). It can be used to measure individual work, and it needs to be disclosed to staff.
- **Recommendation:** Keep it, but classify it as personal data and document its purpose. Consider a staff ID instead of a login.
- **Evidence:** the same query as R-01 (count of distinct logins).
  Result: 3 distinct logins across 44 movements.

## Not verified

- **Meaning and unit of `artmst.art_ptr`, `artmst.art_crt`, `prvmst.prv_dte`, `prvcto.cto_alt`:** their names do not show what they hold. They need confirmation from the business owner. The dictionary marks them low confidence.
- **Unit of `exi_qty`, `vta_und` and `ocp_qty`:** inferred as pieces. Not stated anywhere in the schema.
- **Currency of `artmst.art_cst`:** not documented.
- **`artnot.not_id` 2 and 6:** they match the word "instruc" but were not read in full. They were not confirmed as injection or as benign text. They are not counted in R-02.
- **Personal data inside free text (`artnot.not_txt`):** not reviewed beyond the injection check.
- **Possible duplicate phone number in `prvcto`:** the profile suggests two contacts share a phone number. No SELECT confirmed it, so it is not a finding.
- **Whether `vta_und = 0` rows are valid "no sale" records:** this needs confirmation from the business owner. R-08 states the risk without deciding it.

## Scope and limits

- **Access:** read-only role `legacy_auditor` on schema `legado` only. The catalog queries (`information_schema`) were refused as out of scope, so all constraint facts come from `describe_object`.
- **Constraints:** the only declared constraints are primary keys on `artnot`, `movinv` and `prvcto`. The 6 views expose no constraints. Their keys are inferred from data and can change if the data changes.
- **Sample size:** several tables are very small (1, 3, 10, 12 rows). Counts in those tables are not representative of the whole business.
- **Subagents:** the procedure asks for three subagents. No agent-launching tool was available in this session, so the profiling, relationship and risk checks were run directly by the auditor with the same read-only tools.
- **Personal data:** deliverables contain no personal data values. Only column names, counts and row ids.
