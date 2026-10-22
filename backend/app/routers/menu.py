"""API Router for Menu Item endpoints."""

from typing import List
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.menu import MenuItemCreate, MenuItemOut
from app.services import menu_service

router = APIRouter(prefix="/menu", tags=["Menu"])


@router.get(
    "",
    response_model=List[MenuItemOut],
    summary="List all menu items",
    description="Retrieve list of menu items, optionally filtering only available items.",
)
def list_menu(
    only_available: bool = Query(default=False, description="Filter only available items"),
    db: Session = Depends(get_db),
) -> List[MenuItemOut]:
    return menu_service.list_menu_items(db=db, only_available=only_available)


@router.get(
    "/{item_id}",
    response_model=MenuItemOut,
    summary="Get menu item by ID",
    description="Retrieve details of a single menu item by its database ID.",
)
def get_menu_item(
    item_id: int = Path(..., gt=0, description="Database ID of the menu item"),
    db: Session = Depends(get_db),
) -> MenuItemOut:
    return menu_service.get_menu_item(db=db, item_id=item_id)


@router.post(
    "",
    response_model=MenuItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new menu item",
    description="Add a new dish or beverage to the restaurant menu.",
)
def create_menu_item(
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
) -> MenuItemOut:
    return menu_service.create_menu_item(db=db, data=payload)
