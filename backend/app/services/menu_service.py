"""Service layer for Menu Item business operations."""

from typing import List
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.menu_item import MenuItem
from app.schemas.menu import MenuItemCreate
from app.services.exceptions import ConflictError, NotFoundError


def list_menu_items(db: Session, only_available: bool = False) -> List[MenuItem]:
    """Retrieve all menu items, optionally filtered by availability."""
    query = select(MenuItem).order_by(MenuItem.id)
    if only_available:
        query = query.where(MenuItem.available.is_(True))
    return list(db.scalars(query).all())


def get_menu_item(db: Session, item_id: int) -> MenuItem:
    """Retrieve a single menu item by ID or raise NotFoundError."""
    item = db.get(MenuItem, item_id)
    if item is None:
        raise NotFoundError(
            message=f"Menu item with ID {item_id} not found.",
            code="MENU_ITEM_NOT_FOUND",
        )
    return item


def create_menu_item(db: Session, data: MenuItemCreate) -> MenuItem:
    """Create and persist a new menu item, checking for unique name conflicts."""
    menu_item = MenuItem(
        name=data.name,
        description=data.description,
        price=data.price,
        available=data.available,
    )
    db.add(menu_item)
    try:
        db.commit()
        db.refresh(menu_item)
        return menu_item
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            message=f"Menu item with name '{data.name}' already exists.",
            code="MENU_ITEM_NAME_CONFLICT",
        ) from exc
