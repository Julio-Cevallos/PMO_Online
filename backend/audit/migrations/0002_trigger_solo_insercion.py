"""Protege el historial a nivel de base de datos (RNF-03, D-21).

Un trigger de PostgreSQL rechaza cualquier `UPDATE` o `DELETE` sobre la tabla, venga de la
aplicación, de `manage.py shell` o de una consulta a mano. No es un `CREATE TABLE` (la tabla la crea
el ORM en la migración 0001): solo agrega la regla.

Límites que conviene conocer: no cubre `TRUNCATE` ni a quien sea dueño de la base y pueda quitar el
trigger; eso queda fuera de lo que puede impedir la aplicación.
"""

from django.db import migrations

CREAR = """
CREATE FUNCTION audit_solo_insercion() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'El registro de auditoría es de solo inserción (se intentó %).', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_eventoauditoria_solo_insercion
    BEFORE UPDATE OR DELETE ON audit_eventoauditoria
    FOR EACH ROW EXECUTE FUNCTION audit_solo_insercion();
"""

QUITAR = """
DROP TRIGGER IF EXISTS audit_eventoauditoria_solo_insercion ON audit_eventoauditoria;
DROP FUNCTION IF EXISTS audit_solo_insercion();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(CREAR, reverse_sql=QUITAR)]
