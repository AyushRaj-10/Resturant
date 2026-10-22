#!/usr/bin/env python3
"""Demo helper script to reset database, seed menu, and create 3 sample orders.

Usage:
    python scripts/demo_reset.py --yes
"""

import argparse
from pathlib import Path
import sys

# Ensure backend root is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, select
from app.config import get_settings
from app.database import Base, SessionLocal, engine
import app.models  # noqa: F401 - registers models
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.schemas.order import OrderCreate, OrderItemIn
from app.services.order_service import change_status, create_order
from scripts.seed_menu import INITIAL_MENU_ITEMS


def reset_and_seed(yes_flag: bool = False) -> None:
    settings = get_settings()

    if settings.APP_ENV.lower() == "production":
        print("ERROR: Cannot reset database in production environment (APP_ENV=production).")
        sys.exit(1)

    if not yes_flag:
        print("ERROR: Must pass --yes flag to confirm database reset.")
        sys.exit(1)

    print("Dropping all existing tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print(f"Seeding {len(INITIAL_MENU_ITEMS)} menu items...")
        menu_objs = [MenuItem(**item) for item in INITIAL_MENU_ITEMS]
        db.add_all(menu_objs)
        db.commit()

        # Query seeded menu items to get their IDs
        paneer_tikka = db.scalar(select(MenuItem).where(MenuItem.name == "Paneer Tikka"))
        butter_chicken = db.scalar(select(MenuItem).where(MenuItem.name == "Butter Chicken"))
        garlic_naan = db.scalar(select(MenuItem).where(MenuItem.name == "Garlic Naan"))
        mango_lassi = db.scalar(select(MenuItem).where(MenuItem.name == "Mango Lassi"))
        dal_makhani = db.scalar(select(MenuItem).where(MenuItem.name == "Dal Makhani"))

        # Order 1: PLACED
        order1_in = OrderCreate(
            customer_name="Aarav Sharma",
            table_no=3,
            items=[
                OrderItemIn(menu_item_id=paneer_tikka.id, quantity=2),
                OrderItemIn(menu_item_id=garlic_naan.id, quantity=4),
            ],
        )
        order1 = create_order(db, order1_in)

        # Order 2: PREPARING (PLACED -> PREPARING)
        order2_in = OrderCreate(
            customer_name="Priya Patel",
            table_no=5,
            items=[
                OrderItemIn(menu_item_id=butter_chicken.id, quantity=1),
                OrderItemIn(menu_item_id=garlic_naan.id, quantity=2),
                OrderItemIn(menu_item_id=mango_lassi.id, quantity=2),
            ],
        )
        order2 = create_order(db, order2_in)
        order2 = change_status(db, order2.id, OrderStatus.PREPARING)

        # Order 3: PAID (PLACED -> PREPARING -> SERVED -> PAID)
        order3_in = OrderCreate(
            customer_name="Rohan Verma",
            table_no=8,
            items=[
                OrderItemIn(menu_item_id=dal_makhani.id, quantity=2),
                OrderItemIn(menu_item_id=mango_lassi.id, quantity=1),
            ],
        )
        order3 = create_order(db, order3_in)
        order3 = change_status(db, order3.id, OrderStatus.PREPARING)
        order3 = change_status(db, order3.id, OrderStatus.SERVED)
        order3 = change_status(db, order3.id, OrderStatus.PAID)

        print("\n" + "=" * 50)
        print(" DEMO DATABASE RESET SUCCESSFUL")
        print("=" * 50)
        print(f"Sample Order 1 (PLACED):    ID #{order1.id} | Table {order1.table_no} | {order1.customer_name} | Total: ₹{order1.total_bill}")
        print(f"Sample Order 2 (PREPARING): ID #{order2.id} | Table {order2.table_no} | {order2.customer_name} | Total: ₹{order2.total_bill}")
        print(f"Sample Order 3 (PAID):      ID #{order3.id} | Table {order3.table_no} | {order3.customer_name} | Total: ₹{order3.total_bill}")
        print("=" * 50 + "\n")

    except Exception as exc:
        db.rollback()
        print(f"Error during demo reset: {exc}")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Reset database and seed demo data.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm reset (required to perform destructive wipe).",
    )
    args = parser.parse_args()
    reset_and_seed(yes_flag=args.yes)


if __name__ == "__main__":
    main()
