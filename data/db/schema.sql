PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;
CREATE TABLE customers (
 customer_id INTEGER PRIMARY KEY,
 customer_code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 city TEXT NOT NULL
);
CREATE TABLE products (
 product_id INTEGER PRIMARY KEY,
 sku TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 category TEXT NOT NULL
);
CREATE TABLE orders (
 order_id INTEGER PRIMARY KEY,
 order_number TEXT NOT NULL UNIQUE,
 customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
 order_date TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('completed','cancelled')),
 currency TEXT NOT NULL DEFAULT 'IRR' CHECK(currency='IRR')
);
CREATE TABLE order_items (
 order_item_id INTEGER PRIMARY KEY,
 order_id INTEGER NOT NULL REFERENCES orders(order_id),
 product_id INTEGER NOT NULL REFERENCES products(product_id),
 quantity INTEGER NOT NULL CHECK(quantity>0),
 unit_price_irr INTEGER NOT NULL CHECK(unit_price_irr>=0),
 discount_irr INTEGER NOT NULL DEFAULT 0 CHECK(discount_irr>=0),
 CHECK(discount_irr <= quantity * unit_price_irr)
);
CREATE INDEX idx_orders_date_status ON orders(order_date,status);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
