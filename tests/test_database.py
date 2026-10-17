import hashlib
import sqlite3
import pytest
from app.errors import AppError
from app.tools.database import ReadOnlySQL, authorizer
from app.seed import seed_database
from .fakes import REVENUE_SQL


def test_revenue_completed_and_line_discount(database):
    january = database.execute(REVENUE_SQL, ['completed','2026-01-01','2026-02-01'])
    february = database.execute(REVENUE_SQL, ['completed','2026-02-01','2026-03-01'])
    assert january['rows'] == [{'revenue_irr':100000000}]
    assert february['rows'] == [{'revenue_irr':125000000}]
    assert 'LIMIT 101' in january['executed_sql']


def test_filter_and_join(database):
    result = database.execute('''SELECT o.order_number, c.city FROM orders o
        JOIN customers c ON c.customer_id=o.customer_id
        WHERE c.city=? AND o.status=? ORDER BY o.order_number''', ['Tehran','completed'])
    assert [r['order_number'] for r in result['rows']] == ['N-1001','N-1003','N-1010','N-1012']


def test_aggregation_with_join(database):
    result = database.execute('''SELECT c.city, COUNT(DISTINCT o.order_id) AS orders_count
        FROM customers c JOIN orders o ON o.customer_id=c.customer_id
        JOIN order_items i ON i.order_id=o.order_id
        WHERE o.status=? GROUP BY c.city ORDER BY c.city''', ['completed'])
    assert result['rows'] == [{'city':'Shiraz','orders_count':3},
                             {'city':'Tabriz','orders_count':2}, {'city':'Tehran','orders_count':4}]


def test_nonrecursive_cte(database):
    result = database.execute('WITH x AS (SELECT status FROM orders) SELECT COUNT(*) AS n FROM x')
    assert result['rows'] == [{'n':10}]


def test_truncation(db_path):
    result = ReadOnlySQL(db_path, max_rows=2).execute('SELECT order_number FROM orders ORDER BY order_id')
    assert result['row_count'] == 2 and result['truncated']


def test_empty_is_not_zero(database):
    result = database.execute(REVENUE_SQL, ['completed','2030-01-01','2030-02-01'])
    assert result['rows'] == [{'revenue_irr':None}]


def test_bound_string_does_not_inject(database):
    result = database.execute('SELECT customer_code FROM customers WHERE city=?', ["Tehran' OR 1=1 --"])
    assert result['rows'] == []


@pytest.mark.parametrize('query', [
    'DELETE FROM orders', 'DROP TABLE orders',
    "UPDATE orders SET status='cancelled'", 'INSERT INTO customers VALUES (9,\'x\',\'x\',\'x\')',
    'CREATE TABLE pwned(a)', 'PRAGMA writable_schema=ON', 'PRAGMA table_info(orders)',
    "ATTACH DATABASE ':memory:' AS other", 'VACUUM',
    "SELECT load_extension('/tmp/evil') FROM orders", "SELECT readfile('/etc/passwd') FROM orders",
    "SELECT writefile('/tmp/evil','data') FROM orders", 'SELECT name FROM sqlite_master',
    "SELECT * FROM pragma_table_info('orders')", 'SELECT randomblob(1000000000) FROM orders',
    'SELECT zeroblob(1000000000) FROM orders', 'SELECT * FROM sqlite_dbpage',
    'SELECT order_number FROM orders; DELETE FROM orders',
    'WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT n FROM x',
    'BEGIN TRANSACTION', 'DETACH DATABASE main', 'SELECT 999 AS invented_revenue',
    "SELECT X'0102' AS blob FROM orders", 'SELECT 1e999 AS infinity FROM orders',
])
def test_untrusted_sql_cannot_escape(database, db_path, query):
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    with pytest.raises(AppError):
        database.execute(query)
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 10


@pytest.mark.parametrize('query,params', [('',[]), ('SELECT missing_column FROM orders',[]),
    ('SELECT order_number FROM orders WHERE order_id=?',[]), ('x'*6001,[]),
    ('SELECT order_number FROM orders WHERE order_id=?',[2**80]),
    ('SELECT order_number FROM orders WHERE order_id=?',[float('inf')]),
    ('SELECT order_number FROM orders WHERE order_id=?',[True])])
def test_invalid_input(database, query, params):
    with pytest.raises(AppError):
        database.execute(query, params)


def test_vm_budget(db_path):
    sql = '''SELECT COUNT(*) AS n FROM order_items a CROSS JOIN order_items b
             CROSS JOIN order_items c CROSS JOIN order_items d CROSS JOIN order_items e'''
    with pytest.raises(AppError, match='budget'):
        ReadOnlySQL(db_path, vm_steps=1000).execute(sql)


def test_seed_is_idempotent(db_path, data_dir):
    before = db_path.read_bytes()
    seed_database(data_dir, db_path)
    assert db_path.read_bytes() == before


def test_readonly_connection_is_independent(db_path):
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('DELETE FROM orders')


def test_authorizer_fail_closed():
    assert authorizer(sqlite3.SQLITE_DELETE,'orders',None,'main',None) == sqlite3.SQLITE_DENY
    assert authorizer(sqlite3.SQLITE_READ,'orders','order_id','other',None) == sqlite3.SQLITE_DENY


def test_count_star_engine_empty_column_callback(database):
    assert database.execute('SELECT COUNT(*) AS n FROM orders')['rows'] == [{'n':10}]
    assert authorizer(sqlite3.SQLITE_READ,'orders','secret',None,None) == sqlite3.SQLITE_DENY
