"""Read-only SQL uses SQLite's compiler/authorizer, not keyword filtering.

The model never receives a write connection. Compilation and execution use the
same per-request restricted connection. Database bootstrap is a separate path.
"""
import math
import sqlite3
import time
from pathlib import Path
from ..errors import AppError

SCHEMA = '''
customers(customer_id INTEGER PRIMARY KEY, customer_code TEXT UNIQUE,
          name TEXT, city TEXT)
products(product_id INTEGER PRIMARY KEY, sku TEXT UNIQUE, name TEXT, category TEXT)
orders(order_id INTEGER PRIMARY KEY, order_number TEXT UNIQUE,
       customer_id INTEGER REFERENCES customers(customer_id),
       order_date TEXT, status TEXT, currency TEXT)
order_items(order_item_id INTEGER PRIMARY KEY,
            order_id INTEGER REFERENCES orders(order_id),
            product_id INTEGER REFERENCES products(product_id),
            quantity INTEGER, unit_price_irr INTEGER, discount_irr INTEGER)
'''
RULES = '''
SQLite dialect. All records are fictional. Dates are Gregorian ISO YYYY-MM-DD.
Data covers 2026-01-01 through 2026-03-01. For ambiguous dates ask for clarification;
do not silently translate an unspecified Solar Hijri month into Gregorian dates.
Orders.status is 'completed' or 'cancelled'. Currency is always IRR (Iranian rial).
Revenue = SUM(order_items.quantity * order_items.unit_price_irr - order_items.discount_irr)
for completed orders only, unless the user explicitly requests cancelled orders.
discount_irr is the TOTAL LINE discount, NOT a per-unit discount.
No tax, shipping, costs, refund transactions, profit or inventory quantities exist.
For an absent metric answerable=false; never invent a column or reinterpret revenue as profit.
Join orders.customer_id=customers.customer_id, order_items.order_id=orders.order_id,
order_items.product_id=products.product_id. Avoid multiplying order totals with item joins.
Use distinct order_id when counting orders joined to order_items. Money is integer IRR.
Use business-facing codes/names, not internal IDs, in user-facing projections.
Cities: Tehran, Shiraz, Tabriz. Categories: keyboard, headset, speaker.
English database values may need mapping from the user's Persian language.
Use bound positional '?' parameters for user-provided values, no interpolation.
Use explicit aliases for expressions and distinct column names. No SELECT *.
At most one statement. Non-recursive CTEs, filtering, grouping and joins are supported.
Only basic read functions are permitted: sum, avg, count, min, max, coalesce,
nullif, round, abs, lower, upper, length, substr, substring, strftime, date,
ifnull, like, glob, trim, ltrim, rtrim. No extension/system/schema access.
SQL should extract the facts; when the coordinator requires a calculator, return
base amounts as named numeric columns rather than doing the final percentage in SQL.
'''
ALLOWED_TABLES = {'customers', 'products', 'orders', 'order_items'}
ALLOWED_FUNCTIONS = {'sum', 'avg', 'count', 'min', 'max', 'coalesce', 'nullif', 'round',
                     'abs', 'lower', 'upper', 'length', 'substr', 'substring', 'strftime',
                     'date', 'ifnull', 'like', 'glob', 'trim', 'ltrim', 'rtrim'}


def authorizer(action, arg1, arg2, database, source):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        return (sqlite3.SQLITE_OK if (database == 'main' or (database is None and arg2 == '')) and (arg1 or '').lower() in ALLOWED_TABLES
                else sqlite3.SQLITE_DENY)
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if (arg2 or '').lower() in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


class ReadOnlySQL:
    def __init__(self, path: Path, max_rows: int = 100, timeout_seconds: float = 1,
                 vm_steps: int = 100000):
        self.path = Path(path)
        self.max_rows, self.timeout_seconds, self.vm_steps = max_rows, timeout_seconds, vm_steps

    def execute(self, sql: str, parameters: list | None = None) -> dict:
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 6000 or '\x00' in sql:
            raise AppError('SQL_INVALID', 'SQL is empty, too long or contains invalid characters.', 422)
        parameters = parameters or []
        if not isinstance(parameters, list) or len(parameters) > 100:
            raise AppError('SQL_INVALID', 'Invalid query parameters.', 422)
        for value in parameters:
            if value is not None and type(value) not in (str, int, float):
                raise AppError('SQL_INVALID', 'Invalid parameter type.', 422)
            if isinstance(value, str) and len(value) > 1000:
                raise AppError('SQL_INVALID', 'A query parameter is too long.', 422)
            if isinstance(value, float) and not math.isfinite(value):
                raise AppError('SQL_INVALID', 'Non-finite parameters are not allowed.', 422)
            if type(value) is int and abs(value) > 2**63-1:
                raise AppError('SQL_INVALID', 'An integer parameter is outside SQLite range.', 422)
        if not self.path.is_file():
            raise AppError('DATABASE_UNAVAILABLE', 'The sample database is not initialized.', 503)
        started, steps = time.monotonic(), 0

        def progress():
            nonlocal steps
            steps += 1000
            return int(steps > self.vm_steps or time.monotonic() - started > self.timeout_seconds)

        connection = None
        try:
            uri = self.path.resolve().as_uri() + '?mode=ro'
            connection = sqlite3.connect(uri, uri=True, timeout=self.timeout_seconds)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            if hasattr(connection, 'setconfig') and hasattr(sqlite3, 'SQLITE_DBCONFIG_DEFENSIVE'):
                connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
            if hasattr(connection, 'enable_load_extension'):
                connection.enable_load_extension(False)
            for category, value in [(sqlite3.SQLITE_LIMIT_LENGTH, 100000),
                                    (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 12000),
                                    (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50),
                                    (sqlite3.SQLITE_LIMIT_COLUMN, 100),
                                    (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20),
                                    (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100),
                                    (sqlite3.SQLITE_LIMIT_ATTACHED, 0)]:
                connection.setlimit(category, value)
            reads = set()
            def restricted_authorizer(action, arg1, arg2, database, source):
                decision = authorizer(action, arg1, arg2, database, source)
                if action == sqlite3.SQLITE_READ and decision == sqlite3.SQLITE_OK:
                    reads.add(arg1)
                return decision
            connection.set_authorizer(restricted_authorizer)
            connection.set_progress_handler(progress, 1000)
            # Compile the ORIGINAL query. A write, PRAGMA, ATTACH, extension or
            # internal-table access is denied by the database engine itself.
            connection.execute('EXPLAIN ' + sql, parameters).fetchall()
            if not reads:
                raise AppError('SQL_INVALID', 'A database query must read an approved data table.', 422)
            # This second compilation enforces a query expression and caps output.
            inner = sql.strip().removesuffix(';').strip()
            executed = f'SELECT * FROM ({inner}) AS result LIMIT {self.max_rows + 1}'
            cursor = connection.execute(executed, parameters)
            columns = [item[0] for item in cursor.description]
            # SQLite may rename duplicate subquery columns; require explicit unique
            # aliases at generation time and expose actual returned columns here.
            rows = cursor.fetchmany(self.max_rows + 1)
            truncated = len(rows) > self.max_rows
            result = [dict(zip(columns, row)) for row in rows[:self.max_rows]]
            for row in result:
                for value in row.values():
                    if value is not None and type(value) not in (str, int, float):
                        raise AppError('SQL_INVALID', 'SQL returned an unsupported binary value.', 422)
                    if isinstance(value, float) and not math.isfinite(value):
                        raise AppError('SQL_INVALID', 'SQL returned a non-finite numeric value.', 422)
            import json
            if len(json.dumps(result, ensure_ascii=False)) > 64000:
                raise AppError('SQL_RESULT_LIMIT', 'SQL result exceeds the context size budget.', 422)
            if time.monotonic() - started > self.timeout_seconds:
                raise AppError('SQL_TIMEOUT', 'SQL exceeded its time budget.', 422)
            return {'id': 'sql_1', 'generated_sql': sql, 'executed_sql': executed,
                    'parameters': parameters, 'columns': columns, 'rows': result,
                    'row_count': len(result), 'truncated': truncated,
                    'elapsed_ms': round((time.monotonic()-started)*1000),
                    'currency': 'IRR', 'date_calendar': 'Gregorian'}
        except sqlite3.Error as exc:
            text = str(exc).lower()
            if 'interrupted' in text:
                raise AppError('SQL_TIMEOUT', 'SQL exceeded its time or instruction budget.', 422) from exc
            if any(x in text for x in ('not authorized', 'prohibited', 'readonly', 'authorization denied')):
                raise AppError('SQL_FORBIDDEN', 'Only approved read-only data and functions are permitted.', 422) from exc
            raise AppError('SQL_INVALID', 'SQL could not be compiled or executed against the documented schema.', 422) from exc
        finally:
            if connection is not None:
                connection.close()
