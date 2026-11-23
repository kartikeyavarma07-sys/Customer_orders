"""
Database module for Order Management Web Application.
Handles connection to MongoDB via PyMongo with automatic fallback to local persistent document store
if MongoDB server is offline or unreachable.
"""

import os
import time
import json
import logging
import threading
from datetime import datetime
from bson import ObjectId

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

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "order_management_db")
LOCAL_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "db_store.json")

class JSONDocumentStore:
    """A thread-safe, document-oriented storage engine mimicking MongoDB collections."""
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

    def get_next_sequence(self, seq_name):
        with self.lock:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            counters = data.setdefault("counters", {})
            current = counters.get(seq_name, 1000) + 1
            counters[seq_name] = current
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return current


def _get_nested_val(doc, key):
    """Retrieve values for dotted key path, handling nested dicts and lists of dicts."""
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
    """Evaluate MongoDB comparison operators ($ne, $in, $nin, $gt, $gte, $lt, $lte)."""
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
    """Check if document matches MongoDB-style filter query."""
    if not filter_query:
        return True
    for k, v in filter_query.items():
        if k == "_id":
            if str(doc.get("_id")) != str(v):
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
        if "_id" not in doc:
            doc["_id"] = str(ObjectId())
        else:
            doc["_id"] = str(doc["_id"])
        docs.append(doc)
        self.store._write_data(data)
        
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(doc["_id"])

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


class DatabaseManager:
    def __init__(self):
        self.mongo_client = None
        self.db = None
        self.is_connected = False
        self.connection_message = "Initializing..."
        self.last_connection_attempt = 0
        self.reconnect_cooldown = 30  # seconds cooldown between reconnection attempts
        self.local_store = JSONDocumentStore(LOCAL_STORE_PATH)
        self.connect(force=True)

    def connect(self, force=False):
        now = time.time()
        if not force and not self.is_connected and (now - self.last_connection_attempt < self.reconnect_cooldown):
            return

        self.last_connection_attempt = now
        try:
            import pymongo
            client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=800)
            # Test connection
            client.admin.command('ping')
            self.mongo_client = client
            self.db = client[DB_NAME]
            self.is_connected = True
            self.connection_message = f"Connected to MongoDB server at {MONGO_URI} (DB: {DB_NAME})"
            logger.info(self.connection_message)
            self._ensure_mongo_indexes()
            self._sync_local_to_mongo()
        except Exception as e:
            self.is_connected = False
            self.mongo_client = None
            self.db = None
            self.connection_message = (
                f"MongoDB server at {MONGO_URI} is currently offline or unreachable ({type(e).__name__}). "
                "Operating in Local Persistent Store Mode. Data is safely saved to data/db_store.json."
            )
            logger.warning(self.connection_message)

    def _ensure_mongo_indexes(self):
        if not self.is_connected or self.db is None:
            return
        try:
            self.db.customers.create_index("customer_id", unique=True)
            self.db.customers.create_index("email")
            self.db.items.create_index("item_code", unique=True)
            self.db.orders.create_index("order_number", unique=True)
            self.db.orders.create_index("customer_id")
        except Exception as ex:
            logger.warning(f"Could not build indexes: {ex}")

    def _sync_local_to_mongo(self):
        """Sync any existing records from local store into MongoDB if MongoDB was empty."""
        try:
            import pymongo
            local_customers = self.local_store.get_collection("customers").find()
            if local_customers and self.db.customers.count_documents({}) == 0:
                logger.info("Syncing local store data to MongoDB...")
                for c in local_customers:
                    c_copy = dict(c)
                    if "_id" in c_copy and isinstance(c_copy["_id"], str):
                        try:
                            c_copy["_id"] = ObjectId(c_copy["_id"])
                        except Exception:
                            c_copy.pop("_id", None)
                    try:
                        self.db.customers.insert_one(c_copy)
                    except pymongo.errors.DuplicateKeyError:
                        pass
                for it in self.local_store.get_collection("items").find():
                    it_copy = dict(it)
                    if "_id" in it_copy and isinstance(it_copy["_id"], str):
                        try:
                            it_copy["_id"] = ObjectId(it_copy["_id"])
                        except Exception:
                            it_copy.pop("_id", None)
                    try:
                        self.db.items.insert_one(it_copy)
                    except pymongo.errors.DuplicateKeyError:
                        pass
                for od in self.local_store.get_collection("orders").find():
                    od_copy = dict(od)
                    if "_id" in od_copy and isinstance(od_copy["_id"], str):
                        try:
                            od_copy["_id"] = ObjectId(od_copy["_id"])
                        except Exception:
                            od_copy.pop("_id", None)
                    try:
                        self.db.orders.insert_one(od_copy)
                    except pymongo.errors.DuplicateKeyError:
                        pass
                logger.info("Sync to MongoDB completed successfully.")
        except Exception as e:
            logger.warning(f"Error syncing local data to MongoDB: {e}")

    def get_collection(self, coll_name):
        if not self.is_connected:
            self.connect(force=False)

        if self.is_connected and self.db is not None:
            return self.db[coll_name]
        return self.local_store.get_collection(coll_name)

    def get_status(self):
        return {
            "connected_to_mongodb": self.is_connected,
            "engine": "MongoDB (Native)" if self.is_connected else "Local Persistent JSON/BSON Store",
            "database_name": DB_NAME if self.is_connected else "db_store.json",
            "message": self.connection_message,
            "counts": {
                "customers": self.get_collection("customers").count_documents({}),
                "items": self.get_collection("items").count_documents({}),
                "orders": self.get_collection("orders").count_documents({})
            }
        }


# Singleton database instance
db_manager = DatabaseManager()
