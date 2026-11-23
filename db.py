"""
Database module for Order Management Web Application.
Handles connection to MySQL via PyMySQL with automatic schema initialization
and seamless fallback to local persistent document store if MySQL server is offline or unreachable.
"""

import os
import time
import json
import logging
import threading
from datetime import datetime
import urllib.parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OrderApp.DB")

def _load_dotenv(filepath=None):
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            logger.warning(f"Could not load .env file: {e}")

_load_dotenv()

# MySQL Settings
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "order_management_db")
MYSQL_URL = os.getenv("MYSQL_URL") or os.getenv("DATABASE_URL")

# If MYSQL_URL is provided (e.g. mysql://user:pass@host:port/db), parse it
if MYSQL_URL and MYSQL_URL.startswith("mysql"):
    parsed_url = urllib.parse.urlparse(MYSQL_URL)
    MYSQL_HOST = parsed_url.hostname or MYSQL_HOST
    MYSQL_PORT = parsed_url.port or MYSQL_PORT
    MYSQL_USER = urllib.parse.unquote(parsed_url.username or MYSQL_USER)
    MYSQL_PASSWORD = urllib.parse.unquote(parsed_url.password or MYSQL_PASSWORD)
    db_from_path = parsed_url.path.lstrip("/")
    if db_from_path:
        MYSQL_DB = db_from_path

LOCAL_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "db_store.json")


# -------------------------------------------------------------
# LOCAL STORE FALLBACK ENGINE (when MySQL is offline)
# -------------------------------------------------------------
def _get_nested_val(doc, key):
    parts = key.split(".")
    curr = [doc]
    for p in parts:
        next_curr = []
        for item in curr:
            if isinstance(item, dict) and p in item:
                val = item[p]
                if isinstance(val, list):
                    next_curr.extend(val)
                else:
                    next_curr.append(val)
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict) and p in sub:
                        sval = sub[p]
                        if isinstance(sval, list):
                            next_curr.extend(sval)
                        else:
                            next_curr.append(sval)
        curr = next_curr
    return curr


def _matches_condition(actual, expected):
    if isinstance(expected, dict):
        for op, target in expected.items():
            if op == "$ne" and actual == target:
                return False
            elif op == "$in" and actual not in target:
                return False
            elif op == "$nin" and actual in target:
                return False
            elif op == "$gt" and not (actual > target):
                return False
            elif op == "$gte" and not (actual >= target):
                return False
            elif op == "$lt" and not (actual < target):
                return False
            elif op == "$lte" and not (actual <= target):
                return False
        return True
    return actual == expected


def _doc_matches_filter(doc, filter_query):
    if not filter_query:
        return True
    for k, v in filter_query.items():
        if k in ("_id", "id"):
            if str(doc.get("_id") or doc.get("id")) != str(v):
                return False
            continue
        vals = _get_nested_val(doc, k)
        if not vals:
            if isinstance(v, dict) and "$ne" in v:
                if v["$ne"] is None:
                    return False
            else:
                return False
        else:
            if not any(_matches_condition(val, v) for val in vals):
                return False
    return True


class JSONDocumentStore:
    def __init__(self, filepath):
        self.filepath = filepath
        self.lock = threading.Lock()
        self._ensure_store()

    def _ensure_store(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            initial_data = {
                "customers": [],
                "items": [],
                "orders": [],
                "counters": {"customer_seq": 1000, "item_seq": 100, "order_seq": 1000}
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2, default=str)

    def _read_data(self):
        with self.lock:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)

    def _write_data(self, data):
        with self.lock:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)

    def get_collection(self, coll_name):
        return LocalCollection(self, coll_name)


class LocalCollection:
    def __init__(self, store, coll_name):
        self.store = store
        self.coll_name = coll_name

    def find(self, filter_query=None, sort=None):
        data = self.store._read_data()
        docs = data.get(self.coll_name, [])
        if filter_query:
            result = [dict(doc) for doc in docs if _doc_matches_filter(doc, filter_query)]
        else:
            result = [dict(d) for d in docs]

        if sort:
            for key, direction in reversed(sort):
                result.sort(key=lambda x: x.get(key, ""), reverse=(direction < 0))
        return result

    def find_one(self, filter_query):
        results = self.find(filter_query)
        return results[0] if results else None

    def insert_one(self, document):
        data = self.store._read_data()
        docs = data.setdefault(self.coll_name, [])
        doc = dict(document)
        if "_id" not in doc and "id" not in doc:
            doc["id"] = int(time.time() * 1000) % 1000000000
            doc["_id"] = str(doc["id"])
        elif "_id" in doc and "id" not in doc:
            doc["id"] = doc["_id"]
        docs.append(doc)
        self.store._write_data(data)
        
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(doc.get("id"))

    def update_one(self, filter_query, update_doc):
        data = self.store._read_data()
        docs = data.get(self.coll_name, [])
        matched = False
        for i, doc in enumerate(docs):
            if _doc_matches_filter(doc, filter_query):
                matched = True
                if "$set" in update_doc:
                    doc.update(update_doc["$set"])
                if "$inc" in update_doc:
                    for inc_k, inc_v in update_doc["$inc"].items():
                        doc[inc_k] = doc.get(inc_k, 0) + inc_v
                docs[i] = doc
                break

        if matched:
            self.store._write_data(data)
        
        class UpdateResult:
            def __init__(self, count):
                self.modified_count = count
        return UpdateResult(1 if matched else 0)

    def delete_one(self, filter_query):
        data = self.store._read_data()
        docs = data.get(self.coll_name, [])
        new_docs = []
        deleted = False
        for doc in docs:
            if not deleted and _doc_matches_filter(doc, filter_query):
                deleted = True
                continue
            new_docs.append(doc)

        if deleted:
            data[self.coll_name] = new_docs
            self.store._write_data(data)
        
        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(1 if deleted else 0)

    def delete_many(self, filter_query=None):
        data = self.store._read_data()
        docs = data.get(self.coll_name, [])
        if not filter_query:
            count = len(docs)
            data[self.coll_name] = []
            self.store._write_data(data)
            class DeleteResult:
                def __init__(self, count):
                    self.deleted_count = count
            return DeleteResult(count)

        new_docs = [doc for doc in docs if not _doc_matches_filter(doc, filter_query)]
        deleted_count = len(docs) - len(new_docs)
        if deleted_count > 0:
            data[self.coll_name] = new_docs
            self.store._write_data(data)

        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(deleted_count)

    def count_documents(self, filter_query=None):
        return len(self.find(filter_query))


# -------------------------------------------------------------
# MYSQL DATABASE ENGINE (PyMySQL)
# -------------------------------------------------------------
class MySQLCollection:
    """Provides MongoDB-compatible CRUD interface on top of native MySQL relational tables."""
    def __init__(self, db_manager, table_name):
        self.mgr = db_manager
        self.table = table_name

    def _execute(self, query, params=None, fetch="all"):
        conn = self.mgr._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                if fetch == "all":
                    res = cur.fetchall()
                elif fetch == "one":
                    res = cur.fetchone()
                else:
                    res = cur.rowcount
            conn.commit()
            return res
        except Exception as e:
            conn.rollback()
            raise e

    def find(self, filter_query=None, sort=None):
        sql = f"SELECT * FROM `{self.table}`"
        params = []
        clauses = []

        # Special handling for checking items inside active orders
        if self.table == "orders" and filter_query and "items.item_code" in filter_query:
            item_code = filter_query["items.item_code"]
            status_clause = ""
            if "status" in filter_query and isinstance(filter_query["status"], dict) and "$ne" in filter_query["status"]:
                status_clause = " AND o.status != %s"
                params = [item_code, filter_query["status"]["$ne"]]
            else:
                params = [item_code]
            
            sql = f"""
                SELECT o.* FROM orders o
                JOIN order_items oi ON o.order_number = oi.order_number
                WHERE oi.item_code = %s {status_clause}
            """
            rows = self._execute(sql, params, fetch="all")
            return self._enrich_orders(rows)

        if filter_query:
            for k, v in filter_query.items():
                if isinstance(v, dict):
                    if "$ne" in v:
                        clauses.append(f"`{k}` != %s")
                        params.append(v["$ne"])
                else:
                    clauses.append(f"`{k}` = %s")
                    params.append(v)

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        if sort:
            sort_clauses = []
            for col, direction in sort:
                dir_str = "DESC" if direction < 0 else "ASC"
                sort_clauses.append(f"`{col}` {dir_str}")
            if sort_clauses:
                sql += " ORDER BY " + ", ".join(sort_clauses)

        rows = self._execute(sql, params, fetch="all")
        if self.table == "orders":
            return self._enrich_orders(rows)
        return [dict(r) for r in rows]

    def _enrich_orders(self, orders):
        """Attach line items to order dictionaries from order_items table."""
        if not orders:
            return []
        enriched = []
        for o in orders:
            od = dict(o)
            # Fetch line items
            items = self._execute(
                "SELECT item_code, name, category, price, quantity, subtotal FROM order_items WHERE order_number = %s",
                (od["order_number"],),
                fetch="all"
            )
            od["items"] = [dict(it) for it in items]
            enriched.append(od)
        return enriched

    def find_one(self, filter_query):
        results = self.find(filter_query)
        return results[0] if results else None

    def insert_one(self, document):
        doc = dict(document)
        # Orders table special handling: insert into orders & order_items
        if self.table == "orders":
            items = doc.pop("items", [])
            cols = [k for k in doc.keys() if k not in ("_id", "id")]
            col_names = ", ".join(f"`{c}`" for c in cols)
            placeholders = ", ".join("%s" for _ in cols)
            val_tuple = tuple(doc[c] for c in cols)
            sql = f"INSERT INTO `orders` ({col_names}) VALUES ({placeholders})"
            
            conn = self.mgr._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, val_tuple)
                    inserted_id = cur.lastrowid
                    # Insert order_items
                    for it in items:
                        cur.execute(
                            """INSERT INTO order_items (order_number, item_code, name, category, price, quantity, subtotal)
                               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                            (doc["order_number"], it.get("item_code"), it.get("name"), it.get("category"),
                             it.get("price"), it.get("quantity"), it.get("subtotal"))
                        )
                conn.commit()
                class InsertResult:
                    def __init__(self, iid):
                        self.inserted_id = iid
                return InsertResult(inserted_id)
            except Exception as e:
                conn.rollback()
                raise e

        # Standard tables: customers, items
        cols = [k for k in doc.keys() if k not in ("_id", "id")]
        col_names = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join("%s" for _ in cols)
        val_tuple = tuple(doc[c] for c in cols)
        sql = f"INSERT INTO `{self.table}` ({col_names}) VALUES ({placeholders})"
        
        conn = self.mgr._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, val_tuple)
                inserted_id = cur.lastrowid
            conn.commit()
            class InsertResult:
                def __init__(self, iid):
                    self.inserted_id = iid
            return InsertResult(inserted_id)
        except Exception as e:
            conn.rollback()
            raise e

    def update_one(self, filter_query, update_doc):
        set_clauses = []
        params = []
        if "$set" in update_doc:
            for k, v in update_doc["$set"].items():
                if k not in ("_id", "id"):
                    set_clauses.append(f"`{k}` = %s")
                    params.append(v)
        if "$inc" in update_doc:
            for k, v in update_doc["$inc"].items():
                set_clauses.append(f"`{k}` = `{k}` + %s")
                params.append(v)

        if not set_clauses:
            class EmptyResult:
                modified_count = 0
            return EmptyResult()

        where_clauses = []
        for k, v in filter_query.items():
            where_clauses.append(f"`{k}` = %s")
            params.append(v)

        sql = f"UPDATE `{self.table}` SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)} LIMIT 1"
        rowcount = self._execute(sql, params, fetch="count")
        class UpdateResult:
            def __init__(self, count):
                self.modified_count = count
        return UpdateResult(rowcount)

    def delete_one(self, filter_query):
        where_clauses = []
        params = []
        for k, v in filter_query.items():
            where_clauses.append(f"`{k}` = %s")
            params.append(v)

        # For orders, also cascade delete from order_items
        if self.table == "orders" and "order_number" in filter_query:
            self._execute("DELETE FROM order_items WHERE order_number = %s", (filter_query["order_number"],), fetch="count")

        sql = f"DELETE FROM `{self.table}` WHERE {' AND '.join(where_clauses)} LIMIT 1"
        rowcount = self._execute(sql, params, fetch="count")
        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(rowcount)

    def delete_many(self, filter_query=None):
        if self.table == "orders" and not filter_query:
            self._execute("DELETE FROM order_items", fetch="count")

        if not filter_query:
            sql = f"DELETE FROM `{self.table}`"
            rowcount = self._execute(sql, fetch="count")
        else:
            where_clauses = []
            params = []
            for k, v in filter_query.items():
                where_clauses.append(f"`{k}` = %s")
                params.append(v)
            sql = f"DELETE FROM `{self.table}` WHERE {' AND '.join(where_clauses)}"
            rowcount = self._execute(sql, params, fetch="count")

        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(rowcount)

    def count_documents(self, filter_query=None):
        sql = f"SELECT COUNT(*) as cnt FROM `{self.table}`"
        params = []
        if filter_query:
            clauses = []
            for k, v in filter_query.items():
                clauses.append(f"`{k}` = %s")
                params.append(v)
            sql += " WHERE " + " AND ".join(clauses)
        res = self._execute(sql, params, fetch="one")
        return res["cnt"] if res else 0


class DatabaseManager:
    def __init__(self):
        self.mysql_conn = None
        self.db = None
        self.is_connected = False
        self.connection_message = "Initializing..."
        self.last_connection_attempt = 0
        self.reconnect_cooldown = 15
        self.local_store = JSONDocumentStore(LOCAL_STORE_PATH)
        self.connect(force=True)

    def _get_connection(self):
        if not self.is_connected or not self.mysql_conn:
            self.connect(force=True)
        try:
            self.mysql_conn.ping(reconnect=True)
        except Exception:
            self.connect(force=True)
        return self.mysql_conn

    def connect(self, force=False):
        now = time.time()
        if not force and not self.is_connected and (now - self.last_connection_attempt < self.reconnect_cooldown):
            return

        self.last_connection_attempt = now
        try:
            import pymysql
            import pymysql.cursors

            # Step 1: Connect to MySQL server
            conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=3
            )

            # Step 2: Create Database if not exists
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            conn.select_db(MYSQL_DB)

            self.mysql_conn = conn
            self.db = conn
            self.is_connected = True
            self.connection_message = f"Connected to MySQL database '{MYSQL_DB}' at {MYSQL_HOST}:{MYSQL_PORT}"
            logger.info(self.connection_message)

            self._ensure_mysql_schema()
            self._sync_local_to_mysql()

        except Exception as e:
            self.is_connected = False
            self.mysql_conn = None
            err_msg = str(e)
            if "Access denied" in err_msg:
                self.connection_message = (
                    f"MySQL Access Denied for user '{MYSQL_USER}'@'{MYSQL_HOST}'. "
                    f"Please update MYSQL_PASSWORD in .env. Running in Local Store Mode."
                )
            else:
                self.connection_message = (
                    f"MySQL server at {MYSQL_HOST}:{MYSQL_PORT} is unreachable ({type(e).__name__}). "
                    "Operating in Local Persistent Store Mode. Data is safely saved to data/db_store.json."
                )
            logger.warning(self.connection_message)

    def _ensure_mysql_schema(self):
        if not self.is_connected or not self.mysql_conn:
            return
        conn = self.mysql_conn
        with conn.cursor() as cur:
            # Customers Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `customers` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `customer_id` VARCHAR(50) UNIQUE NOT NULL,
                    `name` VARCHAR(255) NOT NULL,
                    `email` VARCHAR(255) UNIQUE NOT NULL,
                    `phone` VARCHAR(50),
                    `address` VARCHAR(255),
                    `city` VARCHAR(100),
                    `notes` TEXT,
                    `created_at` VARCHAR(50),
                    `updated_at` VARCHAR(50),
                    INDEX `idx_cust_email` (`email`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Items Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `items` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `item_code` VARCHAR(50) UNIQUE NOT NULL,
                    `name` VARCHAR(255) NOT NULL,
                    `category` VARCHAR(100) DEFAULT 'General',
                    `price` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                    `stock` INT NOT NULL DEFAULT 0,
                    `description` TEXT,
                    `created_at` VARCHAR(50),
                    `updated_at` VARCHAR(50),
                    INDEX `idx_item_cat` (`category`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Orders Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `orders` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `order_number` VARCHAR(50) UNIQUE NOT NULL,
                    `customer_id` VARCHAR(50) NOT NULL,
                    `customer_name` VARCHAR(255) NOT NULL,
                    `customer_email` VARCHAR(255),
                    `customer_phone` VARCHAR(50),
                    `customer_address` VARCHAR(255),
                    `customer_city` VARCHAR(100),
                    `item_count` INT DEFAULT 0,
                    `subtotal` DECIMAL(10, 2) DEFAULT 0.00,
                    `discount_pct` DECIMAL(5, 2) DEFAULT 0.00,
                    `discount_amount` DECIMAL(10, 2) DEFAULT 0.00,
                    `tax_pct` DECIMAL(5, 2) DEFAULT 0.00,
                    `tax_amount` DECIMAL(10, 2) DEFAULT 0.00,
                    `total` DECIMAL(10, 2) DEFAULT 0.00,
                    `status` VARCHAR(50) DEFAULT 'Processing',
                    `payment_status` VARCHAR(50) DEFAULT 'Pending',
                    `notes` TEXT,
                    `created_at` VARCHAR(50),
                    `updated_at` VARCHAR(50),
                    INDEX `idx_order_cust` (`customer_id`),
                    INDEX `idx_order_status` (`status`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Order Items Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `order_items` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `order_number` VARCHAR(50) NOT NULL,
                    `item_code` VARCHAR(50) NOT NULL,
                    `name` VARCHAR(255) NOT NULL,
                    `category` VARCHAR(100),
                    `price` DECIMAL(10, 2) NOT NULL,
                    `quantity` INT NOT NULL,
                    `subtotal` DECIMAL(10, 2) NOT NULL,
                    INDEX `idx_oi_ord` (`order_number`),
                    INDEX `idx_oi_item` (`item_code`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
        conn.commit()

    def _sync_local_to_mysql(self):
        """Sync any existing records from local store into MySQL if MySQL was empty."""
        try:
            cust_coll = self.get_collection("customers")
            if cust_coll.count_documents({}) == 0:
                local_custs = self.local_store.get_collection("customers").find()
                for c in local_custs:
                    try:
                        cust_coll.insert_one(c)
                    except Exception:
                        pass

                items_coll = self.get_collection("items")
                local_items = self.local_store.get_collection("items").find()
                for it in local_items:
                    try:
                        items_coll.insert_one(it)
                    except Exception:
                        pass

                orders_coll = self.get_collection("orders")
                local_orders = self.local_store.get_collection("orders").find()
                for od in local_orders:
                    try:
                        orders_coll.insert_one(od)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Error syncing local data to MySQL: {e}")

    def get_collection(self, coll_name):
        if not self.is_connected:
            self.connect(force=False)

        if self.is_connected and self.mysql_conn:
            return MySQLCollection(self, coll_name)
        return self.local_store.get_collection(coll_name)

    def get_status(self):
        return {
            "connected_to_mysql": self.is_connected,
            "engine": "MySQL (Relational)" if self.is_connected else "Local Persistent JSON/BSON Store",
            "database_name": MYSQL_DB if self.is_connected else "db_store.json",
            "host": f"{MYSQL_HOST}:{MYSQL_PORT}" if self.is_connected else "localhost",
            "message": self.connection_message,
            "counts": {
                "customers": self.get_collection("customers").count_documents({}),
                "items": self.get_collection("items").count_documents({}),
                "orders": self.get_collection("orders").count_documents({})
            }
        }


# Singleton database manager instance
db_manager = DatabaseManager()
