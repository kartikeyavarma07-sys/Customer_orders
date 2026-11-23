"""
Automated Integration and Validation Test Suite for OrderFlow.
Verifies all business rules:
- Customer CRUD & uniqueness constraints
- Item CRUD & stock tracking
- Order creation & inventory deduction
- Tax, discount, subtotal, and total accuracy
- Inventory restoration upon order cancellation
- Customer and Item deletion protection
- Dashboard KPI generation
"""

import os
import unittest
import controllers
from db import db_manager, JSONDocumentStore

TEST_STORE_PATH = os.path.join(os.path.dirname(__file__), "data", "test_store.json")


class TestOrderFlowSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Save original state and isolate tests to temporary store
        cls.orig_local_store = db_manager.local_store
        cls.orig_is_connected = db_manager.is_connected
        cls.orig_db = db_manager.db

        if os.path.exists(TEST_STORE_PATH):
            try:
                os.remove(TEST_STORE_PATH)
            except Exception:
                pass

        db_manager.is_connected = False
        db_manager.db = None
        db_manager.local_store = JSONDocumentStore(TEST_STORE_PATH)

    @classmethod
    def tearDownClass(cls):
        # Restore original state and remove temp test store
        db_manager.local_store = cls.orig_local_store
        db_manager.is_connected = cls.orig_is_connected
        db_manager.db = cls.orig_db
        if os.path.exists(TEST_STORE_PATH):
            try:
                os.remove(TEST_STORE_PATH)
            except Exception:
                pass

    def test_01_customer_creation_and_retrieval(self):
        email = "test.tester@domain.com"
        # Create customer
        res, code = controllers.create_customer({
            "name": "Integration Tester",
            "email": email,
            "phone": "+1 555 999 8888",
            "address": "404 Test Road",
            "city": "Denver"
        })
        self.assertEqual(code, 201)
        self.assertIn("customer_id", res)
        cust_id = res["customer_id"]

        # Check retrieval
        cust = controllers.get_customer_by_id(cust_id)
        self.assertIsNotNone(cust)
        self.assertEqual(cust["name"], "Integration Tester")

        # Test duplicate email rejected
        dup_res, dup_code = controllers.create_customer({
            "name": "Another Person",
            "email": email
        })
        self.assertEqual(dup_code, 409)

    def test_02_item_creation_and_stock(self):
        item_code = "TST-UNIT-99"
        res, code = controllers.create_item({
            "item_code": item_code,
            "name": "Super Test Gadget",
            "category": "Electronics",
            "price": 100.0,
            "stock": 20,
            "description": "A gadget for unit testing"
        })
        self.assertEqual(code, 201)
        self.assertEqual(res["item_code"], item_code)

        # Retrieve item
        it = controllers.get_item_by_code(item_code)
        self.assertIsNotNone(it)
        self.assertEqual(it["stock"], 20)
        self.assertEqual(it["price"], 100.0)

    def test_03_order_creation_and_stock_deduction(self):
        # Create customer
        c_res, _ = controllers.create_customer({
            "name": "Order Buyer",
            "email": "buyer.test@domain.com",
            "city": "Austin"
        })
        cust_id = c_res["customer_id"]

        # Create item with 10 in stock
        i_code = "STOCK-TEST-1"
        controllers.create_item({
            "item_code": i_code,
            "name": "Stock Track Product",
            "category": "Accessories",
            "price": 50.0,
            "stock": 10
        })

        # Place Order for 3 units
        # Subtotal = 3 * 50 = 150
        # Discount = 10% -> 15.00
        # Taxable = 135.00
        # Tax = 10% -> 13.50
        # Total = 148.50
        order_res, code = controllers.create_order({
            "customer_id": cust_id,
            "items": [{"item_code": i_code, "quantity": 3}],
            "discount_pct": 10,
            "tax_pct": 10,
            "status": "Processing",
            "payment_status": "Paid"
        })
        self.assertEqual(code, 201)
        self.assertEqual(order_res["subtotal"], 150.0)
        self.assertEqual(order_res["discount_amount"], 15.0)
        self.assertEqual(order_res["tax_amount"], 13.5)
        self.assertEqual(order_res["total"], 148.5)

        # Verify stock was deducted from 10 to 7
        it = controllers.get_item_by_code(i_code)
        self.assertEqual(it["stock"], 7)

    def test_04_order_insufficient_stock_prevention(self):
        # Create customer & item with 2 in stock
        c_res, _ = controllers.create_customer({
            "name": "Greedy Buyer",
            "email": "greedy@domain.com"
        })
        i_code = "LIMITED-QTY-1"
        controllers.create_item({
            "item_code": i_code,
            "name": "Rare Collectible",
            "category": "General",
            "price": 200.0,
            "stock": 2
        })

        # Try to order 5 units (exceeds stock of 2)
        order_res, code = controllers.create_order({
            "customer_id": c_res["customer_id"],
            "items": [{"item_code": i_code, "quantity": 5}]
        })
        self.assertEqual(code, 400)
        self.assertIn("Insufficient stock", order_res["error"])

        # Stock should remain unchanged at 2
        it = controllers.get_item_by_code(i_code)
        self.assertEqual(it["stock"], 2)

    def test_05_cancel_order_restores_inventory(self):
        c_res, _ = controllers.create_customer({
            "name": "Returns Customer",
            "email": "returns@domain.com"
        })
        i_code = "RETURN-ITEM-1"
        controllers.create_item({
            "item_code": i_code,
            "name": "Returnable Item",
            "price": 25.0,
            "stock": 15
        })

        # Order 5 units -> Stock becomes 10
        order, _ = controllers.create_order({
            "customer_id": c_res["customer_id"],
            "items": [{"item_code": i_code, "quantity": 5}],
            "status": "Processing"
        })
        self.assertEqual(controllers.get_item_by_code(i_code)["stock"], 10)

        # Cancel Order -> Stock restored to 15!
        updated_order, code = controllers.update_order_status(order["order_number"], "Cancelled")
        self.assertEqual(code, 200)
        self.assertEqual(updated_order["status"], "Cancelled")
        self.assertEqual(controllers.get_item_by_code(i_code)["stock"], 15)

    def test_06_customer_deletion_safety(self):
        # A customer with active orders must not be deletable
        cust_list = controllers.get_all_customers()
        cust_with_order = None
        for c in cust_list:
            if c.get("order_count", 0) > 0:
                cust_with_order = c
                break

        if cust_with_order:
            del_res, del_code = controllers.delete_customer(cust_with_order["customer_id"])
            self.assertEqual(del_code, 400)
            self.assertIn("Cannot delete customer", del_res["error"])

    def test_07_dashboard_metrics(self):
        summary = controllers.get_dashboard_summary()
        self.assertIn("total_customers", summary)
        self.assertIn("total_items", summary)
        self.assertIn("total_orders", summary)
        self.assertIn("total_revenue", summary)
        self.assertGreater(summary["total_customers"], 0)
        self.assertGreater(summary["total_items"], 0)
        self.assertGreater(summary["total_orders"], 0)
        self.assertGreater(summary["total_revenue"], 0)

    def test_08_item_deletion_safety(self):
        # Create customer & item
        c_res, _ = controllers.create_customer({
            "name": "Safety Tester",
            "email": "safety@tester.com"
        })
        i_code = "SAFE-DEL-1"
        controllers.create_item({
            "item_code": i_code,
            "name": "Safety Item",
            "price": 15.0,
            "stock": 10
        })

        # Place order with this item
        controllers.create_order({
            "customer_id": c_res["customer_id"],
            "items": [{"item_code": i_code, "quantity": 2}],
            "status": "Processing"
        })

        # Attempt to delete item referenced in active order - MUST BE BLOCKED
        del_res, del_code = controllers.delete_item(i_code)
        self.assertEqual(del_code, 400)
        self.assertIn("Cannot delete item", del_res["error"])


if __name__ == "__main__":
    unittest.main()
