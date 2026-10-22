"""Service layer for Generative AI features: confirmations, summaries, bill explanations,
upsell recommendations, descriptions, and natural language order drafting.

Read-only with respect to the database. Never creates, updates, or deletes records.
"""

from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.llm.client import get_llm_client
from app.llm.prompts import (
    BILL_EXPLANATION_SYSTEM_PROMPT,
    CONFIRMATION_SYSTEM_PROMPT,
    DRAFT_ORDER_SYSTEM_PROMPT,
    MENU_DESCRIPTION_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    UPSELL_SYSTEM_PROMPT,
)
from app.models.menu_item import MenuItem
from app.schemas.ai import DraftOrderResponse, TextResponse, UpsellItem, UpsellResponse
from app.schemas.order import OrderCreate, OrderItemIn
from app.services import menu_service, order_rules, order_service
from app.services.exceptions import NotFoundError

# Guard against prompt injection strings in untrusted inputs
PROMPT_INJECTION_PATTERN = re.compile(
    r"(ignore\s+(previous|all)\s+instructions|system\s+prompt|delete\s+all|drop\s+table)",
    re.IGNORECASE,
)


def _contains_injection_attempt(text: str) -> bool:
    """Detect common prompt injection phrasing in inputs or generated outputs."""
    return bool(PROMPT_INJECTION_PATTERN.search(text))


# =========================================================================
# 1. Order Confirmation
# =========================================================================

def generate_confirmation(db: Session, order_id: int) -> TextResponse:
    """Generate a friendly customer confirmation message with strict number guards."""
    order = order_service.get_order(db, order_id)
    items_desc = ", ".join(f"{it.quantity}x {it.menu_item.name}" for it in order.order_items)
    total_str = f"{order.total_bill:.2f}"

    # Deterministic fallback template
    fallback = (
        f"Thank you, {order.customer_name}! Your order for Table {order.table_no} "
        f"({items_desc}) has been placed. Total bill is ₹{total_str}. "
        f"Our kitchen will begin preparing your meal shortly!"
    )

    client = get_llm_client()
    if not client.is_available():
        return TextResponse(message=fallback, source="fallback")

    user_facts = (
        f"Customer: {order.customer_name}\n"
        f"Table Number: {order.table_no}\n"
        f"Items Ordered: {items_desc}\n"
        f"Total Amount: ₹{total_str}\n"
        f"Status: {order.status.value}"
    )

    result = client.generate_text(
        task="order_confirmation",
        system=CONFIRMATION_SYSTEM_PROMPT,
        user_content=user_facts,
        fallback=fallback,
    )

    if result.source == "fallback":
        return TextResponse(message=fallback, source="fallback")

    # Safety checks: injection check & number guard
    if _contains_injection_attempt(result.text) or total_str not in result.text:
        return TextResponse(message=fallback, source="fallback")

    return TextResponse(message=result.text, source="llm")


# =========================================================================
# 2. Order Summary
# =========================================================================

def generate_summary(db: Session, order_id: int) -> TextResponse:
    """Generate a plain-language summary of order status and expected next actions."""
    order = order_service.get_order(db, order_id)
    allowed_actions = order_rules.get_allowed_actions(order.status)
    item_count = sum(it.quantity for it in order.order_items)
    total_str = f"{order.total_bill:.2f}"

    fallback = (
        f"Order #{order.id} for {order.customer_name} (Table {order.table_no}) contains "
        f"{item_count} items totaling ₹{total_str}. "
        f"Current status is {order.status.value}. "
        f"Next valid steps: {', '.join(allowed_actions) if allowed_actions else 'Order complete'}."
    )

    client = get_llm_client()
    if not client.is_available():
        return TextResponse(message=fallback, source="fallback")

    user_facts = (
        f"Order ID: {order.id}\n"
        f"Customer: {order.customer_name}\n"
        f"Table: {order.table_no}\n"
        f"Total Items Count: {item_count}\n"
        f"Total Bill Amount: ₹{total_str}\n"
        f"Status: {order.status.value}\n"
        f"Permitted Next Actions: {', '.join(allowed_actions)}"
    )

    result = client.generate_text(
        task="order_summary",
        system=SUMMARY_SYSTEM_PROMPT,
        user_content=user_facts,
        fallback=fallback,
    )

    if result.source == "fallback":
        return TextResponse(message=fallback, source="fallback")

    # Number guard on total amount
    if _contains_injection_attempt(result.text) or total_str not in result.text:
        return TextResponse(message=fallback, source="fallback")

    return TextResponse(message=result.text, source="llm")


# =========================================================================
# 3. Bill Explanation
# =========================================================================

def explain_bill(db: Session, order_id: int) -> TextResponse:
    """Generate a transparent explanation of the bill breakdown."""
    order = order_service.get_order(db, order_id)
    subtotal = sum(
        (Decimal(it.quantity) * it.price_at_order_time for it in order.order_items),
        start=Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    discount_str = f"{order.discount_percent:.2f}%" if order.discount_percent else "None"
    discount_amt = (
        (subtotal * order.discount_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if order.discount_percent
        else Decimal("0.00")
    )

    service_str = f"{order.service_charge_percent:.2f}%" if order.service_charge_percent else "None"
    service_amt = (
        (subtotal * order.service_charge_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if order.service_charge_percent
        else Decimal("0.00")
    )

    total_str = f"{order.total_bill:.2f}"

    parts = [f"Items Subtotal: ₹{subtotal:.2f}"]
    if order.discount_percent:
        parts.append(f"Discount ({discount_str}): -₹{discount_amt:.2f}")
    if order.service_charge_percent:
        parts.append(f"Service Charge ({service_str}): +₹{service_amt:.2f}")
    parts.append(f"Final Total Payable: ₹{total_str}")

    fallback = (
        f"Bill breakdown for Order #{order.id}: {', '.join(parts)}."
    )

    client = get_llm_client()
    if not client.is_available():
        return TextResponse(message=fallback, source="fallback")

    user_facts = (
        f"Subtotal: ₹{subtotal:.2f}\n"
        f"Discount Percent: {discount_str}\n"
        f"Discount Amount: ₹{discount_amt:.2f}\n"
        f"Service Charge Percent: {service_str}\n"
        f"Service Charge Amount: ₹{service_amt:.2f}\n"
        f"Total Bill: ₹{total_str}"
    )

    result = client.generate_text(
        task="bill_explanation",
        system=BILL_EXPLANATION_SYSTEM_PROMPT,
        user_content=user_facts,
        fallback=fallback,
    )

    if result.source == "fallback":
        return TextResponse(message=fallback, source="fallback")

    # Number guard: every amount in the facts must appear in the output, else fallback
    required_amounts = [f"{subtotal:.2f}", total_str]
    if discount_amt > 0:
        required_amounts.append(f"{discount_amt:.2f}")
    if service_amt > 0:
        required_amounts.append(f"{service_amt:.2f}")

    if (
        _contains_injection_attempt(result.text)
        or any(amt not in result.text for amt in required_amounts)
    ):
        return TextResponse(message=fallback, source="fallback")

    return TextResponse(message=result.text, source="llm")


# =========================================================================
# 4. Upsell Suggestions
# =========================================================================

class _UpsellItemLLM(BaseModel):
    menu_item_id: int
    reason: str


class _UpsellContainerLLM(BaseModel):
    suggestions: List[_UpsellItemLLM] = Field(default_factory=list)


def suggest_additions(db: Session, order_id: int) -> UpsellResponse:
    """Recommend up to 3 complementary available items not already in the order."""
    order = order_service.get_order(db, order_id)
    ordered_ids = {it.menu_item_id for it in order.order_items}

    all_available = menu_service.list_menu_items(db, only_available=True)
    candidate_items = [it for it in all_available if it.id not in ordered_ids]
    candidate_map = {it.id: it for it in candidate_items}

    # Deterministic fallback: pick up to 3 available candidates with sensible reasons
    fallback_items: List[UpsellItem] = []
    for candidate in candidate_items[:3]:
        reason = (
            f"Complements your meal perfectly with a rich blend of flavors."
        )
        fallback_items.append(
            UpsellItem(
                menu_item_id=candidate.id,
                menu_item_name=candidate.name,
                price=candidate.price,
                reason=reason,
            )
        )

    client = get_llm_client()
    if not client.is_available() or not candidate_items:
        return UpsellResponse(suggestions=fallback_items, source="fallback")

    ordered_summary = ", ".join(it.menu_item.name for it in order.order_items)
    candidates_summary = "\n".join(
        f"ID {it.id}: {it.name} (₹{it.price:.2f}) - {it.description or ''}"
        for it in candidate_items
    )

    user_facts = (
        f"Ordered Items: {ordered_summary}\n\n"
        f"Candidate Available Items to Choose From:\n{candidates_summary}"
    )

    parsed, result = client.generate_json(
        task="upsell_suggestions",
        system=UPSELL_SYSTEM_PROMPT,
        user_content=user_facts,
        schema=_UpsellContainerLLM,
        fallback=_UpsellContainerLLM(),
    )

    if not parsed or not parsed.suggestions:
        return UpsellResponse(suggestions=fallback_items, source="fallback")

    # Post-validation: ensure IDs exist, are in candidate_map, and not already ordered
    valid_suggestions: List[UpsellItem] = []
    seen_ids = set()

    for sug in parsed.suggestions:
        item_id = sug.menu_item_id
        if (
            item_id in candidate_map
            and item_id not in ordered_ids
            and item_id not in seen_ids
        ):
            seen_ids.add(item_id)
            matched = candidate_map[item_id]
            valid_suggestions.append(
                UpsellItem(
                    menu_item_id=matched.id,
                    menu_item_name=matched.name,
                    price=matched.price,
                    reason=sug.reason.strip() or "Recommended pairing for your order.",
                )
            )
        if len(valid_suggestions) >= 3:
            break

    if not valid_suggestions:
        return UpsellResponse(suggestions=fallback_items, source="fallback")

    return UpsellResponse(suggestions=valid_suggestions, source="llm")


# =========================================================================
# 5. Menu Item Description
# =========================================================================

def describe_menu_item(db: Session, item_id: int) -> TextResponse:
    """Generate a mouthwatering description for a menu item without persisting it."""
    item = menu_service.get_menu_item(db, item_id)

    fallback = (
        item.description
        if item.description
        else f"{item.name} is prepared fresh daily with authentic spices and finest ingredients."
    )

    client = get_llm_client()
    if not client.is_available():
        return TextResponse(message=fallback, source="fallback")

    user_facts = (
        f"Dish Name: {item.name}\n"
        f"Existing Notes: {item.description or 'Traditional specialty'}\n"
        f"Price: ₹{item.price:.2f}"
    )

    result = client.generate_text(
        task="menu_description",
        system=MENU_DESCRIPTION_SYSTEM_PROMPT,
        user_content=user_facts,
        fallback=fallback,
    )

    if result.source == "fallback" or _contains_injection_attempt(result.text):
        return TextResponse(message=fallback, source="fallback")

    return TextResponse(message=result.text, source="llm")


# =========================================================================
# 6. Natural Language Draft Order
# =========================================================================

class _DraftItemLLM(BaseModel):
    menu_item_id: Optional[int] = None
    item_name: Optional[str] = None
    quantity: int = 1


class _DraftOrderLLM(BaseModel):
    customer_name: Optional[str] = None
    table_no: Optional[int] = None
    items: List[_DraftItemLLM] = Field(default_factory=list)
    unmatched: List[str] = Field(default_factory=list)


def draft_order_from_text(db: Session, text: str) -> DraftOrderResponse:
    """Parse natural language into a proposed OrderCreate draft. Never writes to DB."""
    # Injection detection guard
    if _contains_injection_attempt(text):
        return DraftOrderResponse(
            draft=None,
            unmatched=[],
            warnings=["Security rule: Potential prompt injection or system instruction detected. Request ignored."],
            estimated_total=Decimal("0.00"),
            source="fallback",
            requires_confirmation=True,
        )

    available_items = menu_service.list_menu_items(db, only_available=True)
    item_map: Dict[int, MenuItem] = {it.id: it for it in available_items}
    name_map: Dict[str, MenuItem] = {it.name.lower().strip(): it for it in available_items}

    client = get_llm_client()
    parsed_llm: Optional[_DraftOrderLLM] = None
    source = "fallback"

    if client.is_available():
        menu_catalog = "\n".join(
            f"ID {it.id}: {it.name} (₹{it.price:.2f})" for it in available_items
        )
        user_prompt = f"Available Menu:\n{menu_catalog}\n\nCustomer Request Text:\n{text}"

        parsed_llm, result = client.generate_json(
            task="draft_order",
            system=DRAFT_ORDER_SYSTEM_PROMPT,
            user_content=user_prompt,
            schema=_DraftOrderLLM,
            fallback=None,
        )
        if parsed_llm and result.source == "llm":
            source = "llm"

    # Fallback heuristic parser if LLM is unavailable or failed
    if parsed_llm is None:
        parsed_llm = _heuristic_parse_draft(text, available_items)
        source = "fallback"

    # Assemble structured OrderCreate and calculate total
    warnings: List[str] = []
    unmatched: List[str] = list(parsed_llm.unmatched)
    matched_items_dict: Dict[int, int] = {}  # menu_item_id -> total_quantity

    for item_data in parsed_llm.items:
        matched_item: Optional[MenuItem] = None

        if item_data.menu_item_id and item_data.menu_item_id in item_map:
            matched_item = item_map[item_data.menu_item_id]
        elif item_data.item_name:
            clean_name = item_data.item_name.lower().strip()
            # Exact match or substring match in available names
            if clean_name in name_map:
                matched_item = name_map[clean_name]
            else:
                for key, candidate in name_map.items():
                    if clean_name in key or key in clean_name:
                        matched_item = candidate
                        break

        if matched_item is None:
            unmatched_name = item_data.item_name or (f"Item #{item_data.menu_item_id}" if item_data.menu_item_id else "Unknown item")
            unmatched.append(unmatched_name)
        else:
            qty = max(1, min(50, item_data.quantity))
            matched_items_dict[matched_item.id] = (
                matched_items_dict.get(matched_item.id, 0) + qty
            )

    # Customer Name validation
    cust_name = (parsed_llm.customer_name or "").strip()
    if not cust_name:
        cust_name = "Guest"
        warnings.append("Customer name could not be extracted; defaulted to 'Guest'.")

    # Table Number validation
    tbl_no = parsed_llm.table_no
    if tbl_no is None or tbl_no < 1 or tbl_no > 200:
        tbl_no = 1
        warnings.append("Table number missing or out of range (1-200); defaulted to Table 1.")

    if not matched_items_dict:
        warnings.append("No items from the request matched the available restaurant menu.")
        return DraftOrderResponse(
            draft=None,
            unmatched=unmatched,
            warnings=warnings,
            estimated_total=Decimal("0.00"),
            source=source,
            requires_confirmation=True,
        )

    # Build validated OrderCreate payload
    order_items_in = [
        OrderItemIn(menu_item_id=mid, quantity=qty)
        for mid, qty in matched_items_dict.items()
    ]

    estimated_total = sum(
        (Decimal(qty) * item_map[mid].price for mid, qty in matched_items_dict.items()),
        start=Decimal("0.00"),
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    try:
        draft_payload = OrderCreate(
            customer_name=cust_name,
            table_no=tbl_no,
            items=order_items_in,
        )
        return DraftOrderResponse(
            draft=draft_payload,
            unmatched=unmatched,
            warnings=warnings,
            estimated_total=estimated_total,
            source=source,
            requires_confirmation=True,
        )
    except Exception as exc:
        warnings.append(f"Draft validation error: {str(exc)}")
        return DraftOrderResponse(
            draft=None,
            unmatched=unmatched,
            warnings=warnings,
            estimated_total=estimated_total,
            source=source,
            requires_confirmation=True,
        )


def _heuristic_parse_draft(text: str, available_items: List[MenuItem]) -> _DraftOrderLLM:
    """Regex-based fallback extraction when LLM is unavailable."""
    lower_text = text.lower()
    table_no: Optional[int] = None
    table_match = re.search(r"\btable\s*#?\s*(\d{1,3})\b", lower_text)
    if table_match:
        try:
            table_no = int(table_match.group(1))
        except ValueError:
            table_no = None

    customer_name: Optional[str] = None
    # Matches patterns like "Rahul wants..." or "For Priya, ..."
    name_match = re.search(r"\b(?:for\s+([A-Za-z]+)|([A-Za-z]+)\s+wants|([A-Za-z]+)\s+ordered)\b", text, re.IGNORECASE)
    if name_match:
        for g in name_match.groups():
            if g:
                customer_name = g.capitalize()
                break

    items: List[_DraftItemLLM] = []
    # Match numbers before or after menu item names
    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }

    matched_item_names = set()
    for item in available_items:
        pattern = re.compile(
            rf"(?:(\d+|one|two|three|four|five)\s+)?{re.escape(item.name.lower())}",
            re.IGNORECASE,
        )
        match = pattern.search(lower_text)
        if match:
            raw_qty = match.group(1)
            qty = 1
            if raw_qty:
                if raw_qty.isdigit():
                    qty = int(raw_qty)
                elif raw_qty.lower() in word_to_num:
                    qty = word_to_num[raw_qty.lower()]
            items.append(_DraftItemLLM(menu_item_id=item.id, item_name=item.name, quantity=qty))
            matched_item_names.add(item.name.lower())

    # Detect dishes not on menu (unmatched)
    cleaned = lower_text
    if table_match:
        cleaned = cleaned.replace(table_match.group(0), " ")
    if name_match:
        cleaned = cleaned.replace(name_match.group(0), " ")

    parts = re.split(r"[,;&]|\band\b", cleaned)
    unmatched: List[str] = []
    num_words = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}

    for part in parts:
        part_clean = re.sub(r"^(?:please\s+|also\s+|wants\s+|ordered\s+|have\s+|get\s+)+", "", part.strip()).strip()
        if not part_clean:
            continue
        if any(mname in part_clean for mname in matched_item_names):
            continue
        words = part_clean.split()
        if not words:
            continue
        item_words = words[1:] if (words[0].isdigit() or words[0] in num_words) else words
        candidate = " ".join(item_words).strip()
        if candidate and len(candidate) > 2 and candidate not in {"wants", "order", "food", "table"}:
            unmatched.append(candidate)

    return _DraftOrderLLM(
        customer_name=customer_name,
        table_no=table_no,
        items=items,
        unmatched=unmatched,
    )
