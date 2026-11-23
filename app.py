"""
Full-featured HTTP Web Server and REST API for Customer, Item, and Order Management.
Uses Python standard library HTTPServer with PyMongo and MongoDB database integration.
"""

import os
import sys
import json
import mimetypes
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import logging

import controllers
from db import db_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OrderApp.Server")

PORT = int(os.getenv("PORT", 5000))
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class AppRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body)
        except Exception as e:
            logger.error(f"Failed to parse JSON body: {e}")
            return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ---------------------------------------------------------
    # GET Requests
    # ---------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query_params = urllib.parse.parse_qs(parsed.query)

        def q(key, default=None):
            return query_params.get(key, [default])[0]

        # REST API Routes
        if path == "/api/status":
            return self._send_json(db_manager.get_status())

        elif path == "/api/dashboard":
            return self._send_json(controllers.get_dashboard_summary())

        elif path == "/api/customers":
            search = q("search")
            return self._send_json(controllers.get_all_customers(search))

        elif path.startswith("/api/customers/"):
            cust_id = path.split("/api/customers/")[1]
            cust = controllers.get_customer_by_id(cust_id)
            if cust:
                return self._send_json(cust)
            return self._send_json({"error": "Customer not found"}, 404)

        elif path == "/api/items":
            search = q("search")
            category = q("category")
            return self._send_json(controllers.get_all_items(search, category))

        elif path.startswith("/api/items/"):
            item_code = path.split("/api/items/")[1]
            item = controllers.get_item_by_code(item_code)
            if item:
                return self._send_json(item)
            return self._send_json({"error": "Item not found"}, 404)

        elif path == "/api/orders":
            search = q("search")
            status = q("status")
            return self._send_json(controllers.get_all_orders(search, status))

        elif path.startswith("/api/orders/"):
            order_num = path.split("/api/orders/")[1]
            order = controllers.get_order_by_number(order_num)
            if order:
                return self._send_json(order)
            return self._send_json({"error": "Order not found"}, 404)

        # Fallback to serving static UI files
        if path == "" or path == "/":
            self.path = "/index.html"
        return super().do_GET()

    # ---------------------------------------------------------
    # POST Requests
    # ---------------------------------------------------------
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self._read_json_body()

        if data is None:
            return self._send_json({"error": "Malformed JSON payload"}, 400)

        if path == "/api/customers":
            res, code = controllers.create_customer(data)
            return self._send_json(res, code)

        elif path == "/api/items":
            res, code = controllers.create_item(data)
            return self._send_json(res, code)

        elif path == "/api/orders":
            res, code = controllers.create_order(data)
            return self._send_json(res, code)

        elif path == "/api/db/reconnect":
            db_manager.connect(force=True)
            return self._send_json(db_manager.get_status())

        else:
            return self._send_json({"error": f"Endpoint not found: {path}"}, 404)

    # ---------------------------------------------------------
    # PUT Requests
    # ---------------------------------------------------------
    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self._read_json_body()

        if data is None:
            return self._send_json({"error": "Malformed JSON payload"}, 400)

        if path.startswith("/api/customers/"):
            cust_id = path.split("/api/customers/")[1]
            res, code = controllers.update_customer(cust_id, data)
            return self._send_json(res, code)

        elif path.startswith("/api/items/"):
            item_code = path.split("/api/items/")[1]
            res, code = controllers.update_item(item_code, data)
            return self._send_json(res, code)

        else:
            return self._send_json({"error": f"Endpoint not found: {path}"}, 404)

    # ---------------------------------------------------------
    # PATCH Requests
    # ---------------------------------------------------------
    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self._read_json_body()

        if data is None:
            return self._send_json({"error": "Malformed JSON payload"}, 400)

        if path.startswith("/api/orders/") and path.endswith("/status"):
            parts = path.split("/")
            order_num = parts[3]
            res, code = controllers.update_order_status(
                order_num,
                data.get("status"),
                data.get("payment_status")
            )
            return self._send_json(res, code)

        else:
            return self._send_json({"error": f"Endpoint not found: {path}"}, 404)

    # ---------------------------------------------------------
    # DELETE Requests
    # ---------------------------------------------------------
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/api/customers/"):
            cust_id = path.split("/api/customers/")[1]
            res, code = controllers.delete_customer(cust_id)
            return self._send_json(res, code)

        elif path.startswith("/api/items/"):
            item_code = path.split("/api/items/")[1]
            res, code = controllers.delete_item(item_code)
            return self._send_json(res, code)

        else:
            return self._send_json({"error": f"Endpoint not found: {path}"}, 404)


def run_server(port=PORT):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, AppRequestHandler)
    print(f"============================================================")
    print(f" Order & Inventory Management Web Application")
    print(f" Running at: http://localhost:{port}")
    print(f" Database Status: {db_manager.get_status()['engine']}")
    print(f" Press Ctrl+C to stop the server")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully.")
        httpd.server_close()


if __name__ == "__main__":
    p = PORT
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            pass
    run_server(p)
