"""
Controllers module containing the core business logic for:
- Customers (Create, Read, Update, Delete, Order history)
- Items (Create, Read, Update, Delete, Stock management)
- Orders (Create, Validate stock, Deduct inventory, Calculate totals, Invoice view, Status update)
- Dashboard Metrics (Revenue, counts, low stock alerts)
"""

import time
from datetime import datetime
from db import db_manager


def _serialize(doc):
    """Serialize database record or local store document to JSON-compatible dict."""
    if not doc:
        return None
    d = dict(doc)
    if "_id" in d and "id" not in d:
        d["id"] = d["_id"]
    return d


# -------------------------------------------------------------
# CUSTOMERS CONTROLLER
# -------------------------------------------------------------
def get_all_customers(search_query=None):
    coll = db_manager.get_collection("customers")
    customers = list(coll.find())
    
    # Calculate order counts & total spent per customer
    orders_coll = db_manager.get_collection("orders")
    all_orders = list(orders_coll.find())
    
    order_stats = {}
    for o in all_orders:
        cid = o.get("customer_id")
        if not cid:
            continue
        if cid not in order_stats:
            order_stats[cid] = {"count": 0, "total_spent": 0.0}
        order_stats[cid]["count"] += 1
        if o.get("status") != "Cancelled":
            order_stats[cid]["total_spent"] += float(o.get("total", 0.0))

    result = []
    for c in customers:
        c_ser = _serialize(c)
        cid = c_ser.get("customer_id")
        stats = order_stats.get(cid, {"count": 0, "total_spent": 0.0})
        c_ser["order_count"] = stats["count"]
        c_ser["total_spent"] = round(stats["total_spent"], 2)
        
        # Apply search if given
        if search_query:
            sq = search_query.lower()
            name = c_ser.get("name", "").lower()
            email = c_ser.get("email", "").lower()
            phone = c_ser.get("phone", "").lower()
            cid_str = str(c_ser.get("customer_id", "")).lower()
            if sq not in name and sq not in email and sq not in phone and sq not in cid_str:
                continue

        result.append(c_ser)

    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


def get_customer_by_id(customer_id):
    coll = db_manager.get_collection("customers")
    customer = coll.find_one({"customer_id": customer_id})
    if not customer:
        return None
    
    c_ser = _serialize(customer)
    # Get all orders by this customer
    orders_coll = db_manager.get_collection("orders")
    orders = [_serialize(o) for o in orders_coll.find({"customer_id": customer_id})]
    orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    c_ser["orders"] = orders
    return c_ser


def create_customer(data):
    coll = db_manager.get_collection("customers")
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    address = (data.get("address") or "").strip()
    city = (data.get("city") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not name:
        return {"error": "Customer name is required"}, 400
    if not email:
        return {"error": "Customer email is required"}, 400

    # Check for duplicate email
    existing = coll.find_one({"email": email})
    if existing:
        return {"error": f"A customer with email '{email}' already exists"}, 409

    # Generate customer ID (e.g. CUST-1042)
    seq = int(time.time() * 1000) % 100000
    customer_id = f"CUST-{seq:04d}"
    # Verify uniqueness
    while coll.find_one({"customer_id": customer_id}):
        seq += 1
        customer_id = f"CUST-{seq:04d}"

    now = datetime.now().isoformat()
    doc = {
        "customer_id": customer_id,
        "name": name,
        "email": email,
        "phone": phone,
        "address": address,
        "city": city,
        "notes": notes,
        "created_at": now,
        "updated_at": now
    }
    res = coll.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc, 201


def update_customer(customer_id, data):
    coll = db_manager.get_collection("customers")
    customer = coll.find_one({"customer_id": customer_id})
    if not customer:
        return {"error": "Customer not found"}, 404

    update_fields = {}
    for f in ["name", "phone", "address", "city", "notes"]:
        if f in data:
            update_fields[f] = data[f].strip() if isinstance(data[f], str) else data[f]

    if "email" in data:
        email = data["email"].strip().lower()
        if email != customer.get("email"):
            existing = coll.find_one({"email": email})
            if existing and existing.get("customer_id") != customer_id:
                return {"error": "Email already in use by another customer"}, 409
            update_fields["email"] = email

    if not update_fields:
        return {"message": "No fields to update"}, 200

    update_fields["updated_at"] = datetime.now().isoformat()
    coll.update_one({"customer_id": customer_id}, {"$set": update_fields})
    updated = coll.find_one({"customer_id": customer_id})
    return _serialize(updated), 200


def delete_customer(customer_id):
    coll = db_manager.get_collection("customers")
    customer = coll.find_one({"customer_id": customer_id})
    if not customer:
        return {"error": "Customer not found"}, 404

    orders_coll = db_manager.get_collection("orders")
    orders_count = orders_coll.count_documents({"customer_id": customer_id})
    if orders_count > 0:
        return {
            "error": f"Cannot delete customer '{customer.get('name')}'. They have {orders_count} associated order(s)."
        }, 400

    coll.delete_one({"customer_id": customer_id})
    return {"message": f"Customer '{customer_id}' deleted successfully"}, 200


# -------------------------------------------------------------
# ITEMS CONTROLLER
# -------------------------------------------------------------
def get_all_items(search_query=None, category=None):
    coll = db_manager.get_collection("items")
    items = list(coll.find())
    result = []
    for it in items:
        it_ser = _serialize(it)
        # Add stock status
        stock = int(it_ser.get("stock", 0))
        if stock <= 0:
            it_ser["stock_status"] = "out_of_stock"
        elif stock <= 5:
            it_ser["stock_status"] = "low_stock"
        else:
            it_ser["stock_status"] = "in_stock"

        if category and category.lower() != "all":
            if it_ser.get("category", "").lower() != category.lower():
                continue

        if search_query:
            sq = search_query.lower()
            code = it_ser.get("item_code", "").lower()
            name = it_ser.get("name", "").lower()
            cat = it_ser.get("category", "").lower()
            desc = it_ser.get("description", "").lower()
            if sq not in code and sq not in name and sq not in cat and sq not in desc:
                continue

        result.append(it_ser)

    result.sort(key=lambda x: x.get("name", "").lower())
    return result


def get_item_by_code(item_code):
    coll = db_manager.get_collection("items")
    item = coll.find_one({"item_code": item_code})
    if not item:
        return None
    it_ser = _serialize(item)
    stock = int(it_ser.get("stock", 0))
    if stock <= 0:
        it_ser["stock_status"] = "out_of_stock"
    elif stock <= 5:
        it_ser["stock_status"] = "low_stock"
    else:
        it_ser["stock_status"] = "in_stock"
    return it_ser


def create_item(data):
    coll = db_manager.get_collection("items")
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "General").strip()
    description = (data.get("description") or "").strip()
    item_code = (data.get("item_code") or "").strip().upper()

    try:
        price = round(float(data.get("price", 0)), 2)
    except (ValueError, TypeError):
        return {"error": "Invalid price value"}, 400

    try:
        stock = int(data.get("stock", 0))
    except (ValueError, TypeError):
        return {"error": "Invalid stock quantity"}, 400

    if not name:
        return {"error": "Item name is required"}, 400
    if price < 0:
        return {"error": "Price cannot be negative"}, 400
    if stock < 0:
        return {"error": "Stock cannot be negative"}, 400

    if not item_code:
        seq = int(time.time() * 1000) % 10000
        item_code = f"ITM-{seq:04d}"
        while coll.find_one({"item_code": item_code}):
            seq += 1
            item_code = f"ITM-{seq:04d}"
    else:
        if coll.find_one({"item_code": item_code}):
            return {"error": f"Item code '{item_code}' already exists"}, 409

    now = datetime.now().isoformat()
    doc = {
        "item_code": item_code,
        "name": name,
        "category": category,
        "price": price,
        "stock": stock,
        "description": description,
        "created_at": now,
        "updated_at": now
    }
    res = coll.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return doc, 201


def update_item(item_code, data):
    coll = db_manager.get_collection("items")
    item = coll.find_one({"item_code": item_code})
    if not item:
        return {"error": "Item not found"}, 404

    update_fields = {}
    if "name" in data and data["name"].strip():
        update_fields["name"] = data["name"].strip()
    if "category" in data and data["category"].strip():
        update_fields["category"] = data["category"].strip()
    if "description" in data:
        update_fields["description"] = data["description"].strip()
    if "price" in data:
        try:
            p = round(float(data["price"]), 2)
            if p < 0:
                return {"error": "Price cannot be negative"}, 400
            update_fields["price"] = p
        except (ValueError, TypeError):
            return {"error": "Invalid price value"}, 400
    if "stock" in data:
        try:
            s = int(data["stock"])
            if s < 0:
                return {"error": "Stock cannot be negative"}, 400
            update_fields["stock"] = s
        except (ValueError, TypeError):
            return {"error": "Invalid stock value"}, 400

    if not update_fields:
        return {"message": "No fields to update"}, 200

    update_fields["updated_at"] = datetime.now().isoformat()
    coll.update_one({"item_code": item_code}, {"$set": update_fields})
    updated = coll.find_one({"item_code": item_code})
    return _serialize(updated), 200


def delete_item(item_code):
    coll = db_manager.get_collection("items")
    item = coll.find_one({"item_code": item_code})
    if not item:
        return {"error": "Item not found"}, 404

    # Check if item exists in active orders
    orders_coll = db_manager.get_collection("orders")
    orders = orders_coll.find({"items.item_code": item_code, "status": {"$ne": "Cancelled"}})
    if len(list(orders)) > 0:
        return {
            "error": f"Cannot delete item '{item_code}'. It is referenced in existing active order(s)."
        }, 400

    coll.delete_one({"item_code": item_code})
    return {"message": f"Item '{item_code}' deleted successfully"}, 200


# -------------------------------------------------------------
# ORDERS CONTROLLER
# -------------------------------------------------------------
def get_all_orders(search_query=None, status=None):
    coll = db_manager.get_collection("orders")
    orders = list(coll.find())
    result = []
    for od in orders:
        od_ser = _serialize(od)

        if status and status.lower() != "all":
            if od_ser.get("status", "").lower() != status.lower():
                continue

        if search_query:
            sq = search_query.lower()
            ord_num = od_ser.get("order_number", "").lower()
            cname = od_ser.get("customer_name", "").lower()
            cemail = od_ser.get("customer_email", "").lower()
            if sq not in ord_num and sq not in cname and sq not in cemail:
                continue

        result.append(od_ser)

    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result


def get_order_by_number(order_number):
    coll = db_manager.get_collection("orders")
    order = coll.find_one({"order_number": order_number})
    if not order:
        return None
    return _serialize(order)


def create_order(data):
    """
    Creates an order, validates customer and item inventory,
    deducts stock from database, calculates taxes and totals,
    and returns created order.
    """
    customer_id = (data.get("customer_id") or "").strip()
    raw_items = data.get("items", [])
    discount_pct = float(data.get("discount_pct", 0) or 0)
    tax_pct = float(data.get("tax_pct", 5) or 0)  # Default 5% tax
    notes = (data.get("notes") or "").strip()
    payment_status = (data.get("payment_status") or "Pending").strip()
    order_status = (data.get("status") or "Processing").strip()

    if not customer_id:
        return {"error": "Please select a customer"}, 400
    if not raw_items or not isinstance(raw_items, list):
        return {"error": "Order must contain at least one item"}, 400

    cust_coll = db_manager.get_collection("customers")
    customer = cust_coll.find_one({"customer_id": customer_id})
    if not customer:
        return {"error": f"Customer '{customer_id}' not found"}, 404

    items_coll = db_manager.get_collection("items")
    order_items = []
    subtotal = 0.0

    # Phase 1: Validation of items and stock
    for entry in raw_items:
        icode = (entry.get("item_code") or "").strip()
        try:
            qty = int(entry.get("quantity", 0))
        except (ValueError, TypeError):
            return {"error": f"Invalid quantity for item {icode}"}, 400

        if qty <= 0:
            return {"error": f"Quantity for item {icode} must be at least 1"}, 400

        item_doc = items_coll.find_one({"item_code": icode})
        if not item_doc:
            return {"error": f"Item with code '{icode}' not found"}, 404

        current_stock = int(item_doc.get("stock", 0))
        if current_stock < qty:
            return {
                "error": f"Insufficient stock for '{item_doc.get('name')} ({icode})'. Available: {current_stock}, Requested: {qty}"
            }, 400

        price = float(item_doc.get("price", 0.0))
        line_total = round(price * qty, 2)
        subtotal += line_total

        order_items.append({
            "item_code": icode,
            "name": item_doc.get("name"),
            "category": item_doc.get("category"),
            "price": price,
            "quantity": qty,
            "subtotal": line_total
        })

    # Phase 2: Deduct stock from inventory
    for it in order_items:
        items_coll.update_one(
            {"item_code": it["item_code"]},
            {"$inc": {"stock": -it["quantity"]}}
        )

    # Phase 3: Financial Calculations
    discount_amount = round(subtotal * (discount_pct / 100.0), 2)
    taxable_amount = max(0.0, subtotal - discount_amount)
    tax_amount = round(taxable_amount * (tax_pct / 100.0), 2)
    grand_total = round(taxable_amount + tax_amount, 2)

    # Generate Order Number (ORD-YYYY-XXXX)
    year = datetime.now().year
    seq = int(time.time() * 1000) % 100000
    order_number = f"ORD-{year}-{seq:05d}"
    orders_coll = db_manager.get_collection("orders")
    while orders_coll.find_one({"order_number": order_number}):
        seq += 1
        order_number = f"ORD-{year}-{seq:05d}"

    now = datetime.now().isoformat()
    order_doc = {
        "order_number": order_number,
        "customer_id": customer_id,
        "customer_name": customer.get("name"),
        "customer_email": customer.get("email"),
        "customer_phone": customer.get("phone"),
        "customer_address": customer.get("address"),
        "customer_city": customer.get("city"),
        "items": order_items,
        "item_count": sum(it["quantity"] for it in order_items),
        "subtotal": round(subtotal, 2),
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "tax_pct": tax_pct,
        "tax_amount": tax_amount,
        "total": grand_total,
        "status": order_status,
        "payment_status": payment_status,
        "notes": notes,
        "created_at": now,
        "updated_at": now
    }

    res = orders_coll.insert_one(order_doc)
    order_doc["_id"] = str(res.inserted_id)
    return order_doc, 201


def update_order_status(order_number, new_status, new_payment_status=None):
    orders_coll = db_manager.get_collection("orders")
    order = orders_coll.find_one({"order_number": order_number})
    if not order:
        return {"error": "Order not found"}, 404

    old_status = order.get("status")
    update_fields = {}

    if new_status:
        update_fields["status"] = new_status
        # If order was cancelled, restore inventory stock!
        if new_status == "Cancelled" and old_status != "Cancelled":
            items_coll = db_manager.get_collection("items")
            for it in order.get("items", []):
                items_coll.update_one(
                    {"item_code": it["item_code"]},
                    {"$inc": {"stock": it["quantity"]}}
                )
        # If order was previously cancelled and is now reopened, re-deduct stock
        elif old_status == "Cancelled" and new_status != "Cancelled":
            items_coll = db_manager.get_collection("items")
            # First check if sufficient stock is available
            for it in order.get("items", []):
                curr = items_coll.find_one({"item_code": it["item_code"]})
                if curr and curr.get("stock", 0) < it["quantity"]:
                    return {
                        "error": f"Cannot reactivate order: insufficient stock for item {it['item_code']}"
                    }, 400
            for it in order.get("items", []):
                items_coll.update_one(
                    {"item_code": it["item_code"]},
                    {"$inc": {"stock": -it["quantity"]}}
                )

    if new_payment_status:
        update_fields["payment_status"] = new_payment_status

    if not update_fields:
        return {"message": "No updates specified"}, 200

    update_fields["updated_at"] = datetime.now().isoformat()
    orders_coll.update_one({"order_number": order_number}, {"$set": update_fields})
    updated = orders_coll.find_one({"order_number": order_number})
    return _serialize(updated), 200


# -------------------------------------------------------------
# DASHBOARD / STATS
# -------------------------------------------------------------
def get_dashboard_summary():
    customers_coll = db_manager.get_collection("customers")
    items_coll = db_manager.get_collection("items")
    orders_coll = db_manager.get_collection("orders")

    customers_count = customers_coll.count_documents({})
    items_count = items_coll.count_documents({})
    orders_count = orders_coll.count_documents({})

    all_orders = list(orders_coll.find())
    total_revenue = 0.0
    pending_orders = 0
    completed_orders = 0

    for o in all_orders:
        st = o.get("status")
        tot = float(o.get("total", 0.0))
        if st != "Cancelled":
            total_revenue += tot
        if st == "Processing" or st == "Pending":
            pending_orders += 1
        elif st == "Completed":
            completed_orders += 1

    # Low stock items
    all_items = list(items_coll.find())
    low_stock = []
    for it in all_items:
        s = int(it.get("stock", 0))
        if s <= 5:
            low_stock.append({
                "item_code": it.get("item_code"),
                "name": it.get("name"),
                "stock": s,
                "price": it.get("price")
            })

    # Recent orders (latest 5)
    recent_orders = [_serialize(o) for o in all_orders]
    recent_orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    recent_orders = recent_orders[:5]

    return {
        "total_customers": customers_count,
        "total_items": items_count,
        "total_orders": orders_count,
        "total_revenue": round(total_revenue, 2),
        "pending_orders": pending_orders,
        "completed_orders": completed_orders,
        "low_stock_items": low_stock,
        "recent_orders": recent_orders,
        "db_status": db_manager.get_status()
    }
