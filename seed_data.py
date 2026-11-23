"""
Seed script to pre-populate sample Customers, Items, and Orders.
Run this script with: python seed_data.py
"""

from db import db_manager
import controllers

def seed():
    print("🌱 Starting Database Seeding...")

    # Clean slate for fresh seeding
    customers_coll = db_manager.get_collection("customers")
    items_coll = db_manager.get_collection("items")
    orders_coll = db_manager.get_collection("orders")
    
    customers_coll.delete_many({})
    items_coll.delete_many({})
    orders_coll.delete_many({})

    sample_customers = [
        {
            "name": "Sarah Jenkins",
            "email": "sarah.j@example.com",
            "phone": "+1 (555) 234-5678",
            "address": "742 Evergreen Terrace",
            "city": "Springfield",
            "notes": "VIP Corporate Client"
        },
        {
            "name": "Michael Chang",
            "email": "m.chang@techpulse.io",
            "phone": "+1 (555) 876-5432",
            "address": "120 Silicon Way, Suite 400",
            "city": "San Jose",
            "notes": "Prefers priority shipping"
        },
        {
            "name": "Emma Watson",
            "email": "emma.watson@designhub.co",
            "phone": "+1 (555) 345-6789",
            "address": "45 Kensington Crescent",
            "city": "London",
            "notes": "Monthly recurring purchaser"
        },
        {
            "name": "Rajesh Kumar",
            "email": "rajesh.kumar@infotech.in",
            "phone": "+91 98765 43210",
            "address": "Plot 14, Electronic City",
            "city": "Bengaluru",
            "notes": "Bulk office supplier"
        },
        {
            "name": "Olivia Martinez",
            "email": "olivia.m@creativeworks.net",
            "phone": "+1 (555) 901-2345",
            "address": "88 Ocean Drive",
            "city": "Miami",
            "notes": "New customer via referral"
        }
    ]

    sample_items = [
        {
            "item_code": "LAP-001",
            "name": "ProBook Ultra 15-inch Laptop",
            "category": "Electronics",
            "price": 1299.99,
            "stock": 25,
            "description": "Intel Core i7 13th Gen, 16GB DDR5 RAM, 512GB NVMe SSD"
        },
        {
            "item_code": "MOU-002",
            "name": "Ergonomic Wireless Mouse",
            "category": "Accessories",
            "price": 49.50,
            "stock": 80,
            "description": "Silent click, dual Bluetooth & 2.4GHz wireless connection"
        },
        {
            "item_code": "KEY-003",
            "name": "RGB Mechanical Keyboard",
            "category": "Accessories",
            "price": 89.00,
            "stock": 45,
            "description": "Hot-swappable brown switches with detachable USB-C cable"
        },
        {
            "item_code": "MON-004",
            "name": "4K Ultra-Wide Monitor 34\"",
            "category": "Electronics",
            "price": 549.99,
            "stock": 12,
            "description": "Curved IPS display, 144Hz refresh rate, USB-C 90W power delivery"
        },
        {
            "item_code": "CHR-005",
            "name": "ErgoComfort Office Chair",
            "category": "Furniture",
            "price": 289.00,
            "stock": 4,  # low stock
            "description": "Breathable mesh back with adjustable lumbar support and 3D armrests"
        },
        {
            "item_code": "DSK-006",
            "name": "Motorized Standing Desk",
            "category": "Furniture",
            "price": 450.00,
            "stock": 8,
            "description": "Dual-motor electric height adjustment, walnut tabletop 140x70cm"
        },
        {
            "item_code": "NOT-007",
            "name": "Executive Hardcover Notebook",
            "category": "Stationery",
            "price": 14.99,
            "stock": 150,
            "description": "160 pages, 120gsm acid-free bleedproof paper with pen loop"
        },
        {
            "item_code": "PEN-008",
            "name": "Precision Gel Pens (Set of 6)",
            "category": "Stationery",
            "price": 9.99,
            "stock": 3,  # low stock
            "description": "0.5mm quick-dry black ink pens for smooth documentation"
        }
    ]

    print("\n1. Creating Customers...")
    created_customers = []
    for c in sample_customers:
        res, code = controllers.create_customer(c)
        if code == 201:
            print(f"   [+] Created Customer: {res['customer_id']} - {res['name']}")
            created_customers.append(res)
        else:
            print(f"   [-] Failed or already exists: {res}")

    print("\n2. Creating Items...")
    created_items = []
    for it in sample_items:
        res, code = controllers.create_item(it)
        if code == 201:
            print(f"   [+] Created Item: {res['item_code']} - {res['name']} (${res['price']})")
            created_items.append(res)
        else:
            print(f"   [-] Failed or already exists: {res}")

    # Reload customers & items from DB
    cust_list = controllers.get_all_customers()
    item_list = controllers.get_all_items()

    if cust_list and item_list:
        print("\n3. Creating Sample Orders...")
        orders_to_create = [
            {
                "customer_id": cust_list[0]["customer_id"],
                "items": [
                    {"item_code": item_list[0]["item_code"], "quantity": 1},
                    {"item_code": item_list[1]["item_code"], "quantity": 2}
                ],
                "discount_pct": 5,
                "tax_pct": 8,
                "status": "Completed",
                "payment_status": "Paid",
                "notes": "First order discount applied"
            },
            {
                "customer_id": cust_list[1]["customer_id"],
                "items": [
                    {"item_code": item_list[2]["item_code"], "quantity": 2},
                    {"item_code": item_list[3]["item_code"], "quantity": 1}
                ],
                "discount_pct": 0,
                "tax_pct": 8,
                "status": "Processing",
                "payment_status": "Paid",
                "notes": "Express delivery requested"
            },
            {
                "customer_id": cust_list[2]["customer_id"],
                "items": [
                    {"item_code": item_list[4]["item_code"], "quantity": 1},
                    {"item_code": item_list[6]["item_code"], "quantity": 3}
                ],
                "discount_pct": 10,
                "tax_pct": 5,
                "status": "Pending",
                "payment_status": "Pending",
                "notes": "Invoice sent via email"
            }
        ]

        for od in orders_to_create:
            res, code = controllers.create_order(od)
            if code == 201:
                print(f"   [+] Created Order: {res['order_number']} for {res['customer_name']} - Total: ${res['total']}")
            else:
                print(f"   [-] Order creation failed: {res}")

    print("\n✨ Database seeding finished!")
    summary = controllers.get_dashboard_summary()
    print(f"Summary: {summary['total_customers']} Customers, {summary['total_items']} Items, {summary['total_orders']} Orders, Revenue: ${summary['total_revenue']}")

if __name__ == "__main__":
    seed()
