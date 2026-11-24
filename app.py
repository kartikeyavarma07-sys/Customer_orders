"""
Full-featured Web Application and REST API for Customer, Item, and Order Management.
Implements a standard WSGI callable (`app` and `application`) compatible with:
- Vercel Serverless Functions
- Render / Gunicorn / Docker
- Local standalone execution (`python app.py`)
"""

import os
import sys
import json
import mimetypes
import urllib.parse
import logging

import controllers
from db import db_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OrderApp")

PORT = int(os.getenv("PORT", 5000))
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _handle_request(environ, start_response):
    """Internal WSGI request router."""
    method = environ.get("REQUEST_METHOD", "GET").upper()
    raw_path = environ.get("PATH_INFO", "/")
    path = raw_path.rstrip("/")
    if not path:
        path = "/"

    # Handle CORS Preflight
    if method == "OPTIONS":
        headers = [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
        ]
        start_response("204 No Content", headers)
        return [b""]

    def send_json(data, status_code=200):
        status_map = {
            200: "200 OK",
            201: "201 Created",
            204: "204 No Content",
            400: "400 Bad Request",
            404: "404 Not Found",
            409: "409 Conflict",
            500: "500 Internal Server Error"
        }
        status_text = status_map.get(status_code, f"{status_code} Status")
        body = json.dumps(data, default=str).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
            ("Content-Length", str(len(body)))
        ]
        start_response(status_text, headers)
        return [body]

    def read_json():
        try:
            length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            if length <= 0:
                return {}
            raw = environ["wsgi.input"].read(length).decode("utf-8")
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse JSON body: {e}")
            return None

    query_params = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))

    def q(key, default=None):
        return query_params.get(key, [default])[0]

    # ---------------------------------------------------------
    # REST API Routing
    # ---------------------------------------------------------
    if path == "/api/status" and method == "GET":
        return send_json(db_manager.get_status())
    elif path == "/api/ping" and method == "GET":
        return send_json({"message": "pong"})
    elif path == "/api/dashboard" and method == "GET":
        return send_json(controllers.get_dashboard_summary())

    elif path == "/api/customers":
        if method == "GET":
            return send_json(controllers.get_all_customers(q("search")))
        elif method == "POST":
            data = read_json()
            if data is None:
                return send_json({"error": "Malformed JSON payload"}, 400)
            res, code = controllers.create_customer(data)
            return send_json(res, code)

    elif path.startswith("/api/customers/"):
        cust_id = path.split("/api/customers/")[1]
        if method == "GET":
            cust = controllers.get_customer_by_id(cust_id)
            if cust:
                return send_json(cust)
            return send_json({"error": "Customer not found"}, 404)
        elif method == "PUT":
            data = read_json()
            if data is None:
                return send_json({"error": "Malformed JSON payload"}, 400)
            res, code = controllers.update_customer(cust_id, data)
            return send_json(res, code)
        elif method == "DELETE":
            res, code = controllers.delete_customer(cust_id)
            return send_json(res, code)

    elif path == "/api/items":
        if method == "GET":
            return send_json(controllers.get_all_items(q("search"), q("category")))
        elif method == "POST":
            data = read_json()
            if data is None:
                return send_json({"error": "Malformed JSON payload"}, 400)
            res, code = controllers.create_item(data)
            return send_json(res, code)

    elif path.startswith("/api/items/"):
        item_code = path.split("/api/items/")[1]
        if method == "GET":
            item = controllers.get_item_by_code(item_code)
            if item:
                return send_json(item)
            return send_json({"error": "Item not found"}, 404)
        elif method == "PUT":
            data = read_json()
            if data is None:
                return send_json({"error": "Malformed JSON payload"}, 400)
            res, code = controllers.update_item(item_code, data)
            return send_json(res, code)
        elif method == "DELETE":
            res, code = controllers.delete_item(item_code)
            return send_json(res, code)

    elif path == "/api/orders":
        if method == "GET":
            return send_json(controllers.get_all_orders(q("search"), q("status")))
        elif method == "POST":
            data = read_json()
            if data is None:
                return send_json({"error": "Malformed JSON payload"}, 400)
            res, code = controllers.create_order(data)
            return send_json(res, code)

    elif path.startswith("/api/orders/"):
        parts = path.split("/")
        if len(parts) >= 4 and parts[3]:
            order_num = parts[3]
            if len(parts) == 5 and parts[4] == "status" and method == "PATCH":
                data = read_json()
                if data is None:
                    return send_json({"error": "Malformed JSON payload"}, 400)
                res, code = controllers.update_order_status(
                    order_num,
                    data.get("status"),
                    data.get("payment_status")
                )
                return send_json(res, code)
            elif len(parts) == 4 and method == "GET":
                order = controllers.get_order_by_number(order_num)
                if order:
                    return send_json(order)
                return send_json({"error": "Order not found"}, 404)

    elif path == "/api/db/reconnect" and method == "POST":
        db_manager.connect(force=True)
        return send_json(db_manager.get_status())

    # ---------------------------------------------------------
    # Static File Serving (HTML, CSS, JS)
    # ---------------------------------------------------------
    if method == "GET":
        if path == "/" or path == "/index.html":
            file_path = os.path.join(STATIC_DIR, "index.html")
        else:
            rel = path.lstrip("/").replace("/", os.sep)
            file_path = os.path.join(STATIC_DIR, rel)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            with open(file_path, "rb") as f:
                content = f.read()
            headers = [
                ("Content-Type", mime_type),
                ("Content-Length", str(len(content))),
                ("Access-Control-Allow-Origin", "*"),
            ]
            start_response("200 OK", headers)
            return [content]

    # Fallback 404
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]


def app(environ, start_response):
    """Standard WSGI entrypoint required by Vercel, Gunicorn, and WSGI servers."""
    try:
        return _handle_request(environ, start_response)
    except Exception as e:
        logger.error(f"Internal server error handling {environ.get('PATH_INFO')}: {e}", exc_info=True)
        body = json.dumps({"error": "Internal Server Error", "details": str(e)}).encode("utf-8")
        try:
            start_response("500 Internal Server Error", [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Access-Control-Allow-Origin", "*"),
                ("Content-Length", str(len(body)))
            ])
            return [body]
        except Exception:
            return [body]


# Alias for WSGI platforms (Vercel, Gunicorn, uWSGI)
application = app
handler = app


def run_server(port=PORT):
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server

    class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # Suppress noisy broken pipe errors from browser cancellations
            pass

    print("============================================================")
    print(" Order & Inventory Management Web Application")
    print(f" Running at: http://localhost:{port}")
    print(f" Database Status: {db_manager.get_status()['engine']}")
    print(" Press Ctrl+C to stop the server")
    print("============================================================")
    with make_server("0.0.0.0", port, app, server_class=ThreadedWSGIServer) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer shutting down gracefully.")


if __name__ == "__main__":
    p = PORT
    if len(sys.argv) > 1:
        try:
            p = int(sys.argv[1])
        except ValueError:
            pass
    run_server(p)
