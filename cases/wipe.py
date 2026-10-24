from django.core.management.color import no_style
from django.db import connection

from .models import Case


def wipe_cases():
    """Delete every case and restart the case numbers. Does nothing if the table does not exist yet."""
    table = Case._meta.db_table
    if table not in connection.introspection.table_names():
        return
    with connection.cursor() as cursor:
        for statement in connection.ops.sql_flush(no_style(), [table], reset_sequences=True):
            cursor.execute(statement)
