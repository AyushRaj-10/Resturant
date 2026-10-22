#!/usr/bin/env python3
"""Seed script to populate initial menu items if the table is empty."""

from decimal import Decimal
from pathlib import Path
import sys

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select
from app.database import SessionLocal
from app.models.menu_item import MenuItem

INITIAL_MENU_ITEMS = [
    # Starters
    {
        "name": "Paneer Tikka",
        "description": "Marinated cottage cheese cubes grilled in tandoor with capsicum and onions.",
        "price": Decimal("260.00"),
        "available": True,
    },
    {
        "name": "Chicken Tikka",
        "description": "Boneless chicken marinated in spiced yogurt and roasted in clay oven.",
        "price": Decimal("320.00"),
        "available": True,
    },
    {
        "name": "Crispy Corn",
        "description": "Batter-fried sweet corn kernels tossed with spices, onion, and herbs.",
        "price": Decimal("210.00"),
        "available": True,
    },
    # Mains
    {
        "name": "Butter Chicken",
        "description": "Tender chicken cooked in rich, creamy tomato and butter gravy.",
        "price": Decimal("380.00"),
        "available": True,
    },
    {
        "name": "Dal Makhani",
        "description": "Slow-cooked black lentils in butter and cream with aromatic spices.",
        "price": Decimal("270.00"),
        "available": True,
    },
    {
        "name": "Paneer Butter Masala",
        "description": "Cottage cheese simmered in velvety makhani sauce with aromatic fenugreek.",
        "price": Decimal("310.00"),
        "available": True,
    },
    {
        "name": "Mutton Rogan Josh",
        "description": "Traditional Kashmiri mutton curry cooked with aromatic whole spices.",
        "price": Decimal("450.00"),
        "available": True,
    },
    # Breads & Rice
    {
        "name": "Butter Naan",
        "description": "Soft leavened flatbread baked in tandoor and brushed with butter.",
        "price": Decimal("55.00"),
        "available": True,
    },
    {
        "name": "Garlic Naan",
        "description": "Tandoori leavened flatbread topped with minced garlic and coriander.",
        "price": Decimal("65.00"),
        "available": True,
    },
    {
        "name": "Jeera Rice",
        "description": "Fragrant basmati rice tempered with roasted cumin seeds and ghee.",
        "price": Decimal("160.00"),
        "available": True,
    },
    # Desserts
    {
        "name": "Gulab Jamun (2 pcs)",
        "description": "Golden fried milk solids dumplings soaked in rose and cardamom syrup.",
        "price": Decimal("90.00"),
        "available": True,
    },
    {
        "name": "Rasmalai (2 pcs)",
        "description": "Flattened chenna discs soaked in thickened saffron-cardamom milk.",
        "price": Decimal("120.00"),
        "available": True,
    },
    # Beverages
    {
        "name": "Masala Chai",
        "description": "Freshly brewed Indian tea with ginger, cardamom, and whole spices.",
        "price": Decimal("40.00"),
        "available": True,
    },
    {
        "name": "Mango Lassi",
        "description": "Thick chilled yogurt beverage blended with sweet mango pulp.",
        "price": Decimal("95.00"),
        "available": True,
    },
]


def seed_menu() -> None:
    """Populate menu_items table if it is currently empty."""
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count(MenuItem.id)))
        if count and count > 0:
            print(f"menu_items table already contains {count} items. Skipping seeding (idempotent).")
            return

        print(f"Seeding {len(INITIAL_MENU_ITEMS)} menu items...")
        items = [MenuItem(**item) for item in INITIAL_MENU_ITEMS]
        db.add_all(items)
        db.commit()
        print("Successfully seeded menu items:")
        for item in items:
            print(f" - {item.name}: ₹{item.price:.2f}")
    except Exception as exc:
        db.rollback()
        print(f"Error seeding menu items: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_menu()
