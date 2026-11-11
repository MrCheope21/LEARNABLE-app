"""Paid courses: taking the buyer's payment and paying the author (docs/MARKETPLACE.md §8).

LEARNABLE never holds card data or the author's money. With PAYMENTS_PROVIDER=stripe:

    author  → "Set up payments" → their own Stripe account (Connect Express), onboarded on
              Stripe's pages; `users.payout_ready` once Stripe says it can take payments
    buyer   → "Buy" → a MarketplaceOrder (PENDING) and a Stripe Checkout page; the charge goes
              to the author's account minus PLATFORM_FEE_PERCENT
    Stripe  → webhook → the order becomes PAID and only then is access given

Access is never given from the browser's return to the site: only the signed webhook counts.
With PAYMENTS_PROVIDER=none (the default) every course is free and a price can't be set.
"""

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ConflictError, InvalidRequestError, NotFoundError
from app.db.types import utc_now
from app.models.marketplace import MarketplaceAcquisition, MarketplaceListing, MarketplaceOrder
from app.models.user import User
from app.schemas.marketplace import PayoutStatus, Sale, Sales
from app.services import notifications

PENDING, PAID, EXPIRED, REFUNDED = "PENDING", "PAID", "EXPIRED", "REFUNDED"
SIGNATURE_TOLERANCE = 300


class PaymentsUnavailableError(AppError):
    status_code = 503
    error_type = "payments_unavailable"


@dataclass(frozen=True)
class Checkout:
    session_id: str
    url: str


@dataclass(frozen=True)
class PaymentEvent:
    # "paid", "expired", "refunded" or "seller_updated".
    kind: str
    session_id: str | None = None
    payment_id: str | None = None
    account_id: str | None = None
    seller_ready: bool = False


class PaymentGateway(Protocol):
    name: str

    def create_seller_account(self, email: str) -> str: ...

    def onboarding_link(self, account_id: str, return_url: str) -> str: ...

    def seller_ready(self, account_id: str) -> bool: ...

    def create_checkout(
        self,
        *,
        order_id: uuid.UUID,
        title: str,
        amount_cents: int,
        fee_cents: int,
        currency: str,
        seller_account: str,
        buyer_email: str,
        success_url: str,
        cancel_url: str,
    ) -> Checkout: ...

    def parse_event(self, payload: bytes, signature: str) -> PaymentEvent | None: ...


class StripeGateway:
    """Stripe's HTTP API, called directly (form-encoded), so there is no SDK to keep up."""

    name = "stripe"
    base_url = "https://api.stripe.com/v1"

    def __init__(self, secret_key: str, webhook_secret: str, timeout: float = 20) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._timeout = timeout

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, data)

    def _request(self, method: str, path: str, data: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                data=data,
                auth=(self._secret_key, ""),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise PaymentsUnavailableError("The payment service can't be reached.") from exc
        if response.status_code >= 400:
            # Stripe's message may name internal ids: keep it out of the answer.
            raise PaymentsUnavailableError("The payment service refused the request.")
        result: dict[str, Any] = response.json()
        return result

    def create_seller_account(self, email: str) -> str:
        account = self._post(
            "/accounts",
            {
                "type": "express",
                "email": email,
                "capabilities[card_payments][requested]": "true",
                "capabilities[transfers][requested]": "true",
            },
        )
        return str(account["id"])

    def onboarding_link(self, account_id: str, return_url: str) -> str:
        link = self._post(
            "/account_links",
            {
                "account": account_id,
                "type": "account_onboarding",
                "return_url": return_url,
                "refresh_url": return_url,
            },
        )
        return str(link["url"])

    def seller_ready(self, account_id: str) -> bool:
        account = self._request("GET", f"/accounts/{account_id}", None)
        return bool(account.get("charges_enabled")) and bool(account.get("details_submitted"))

    def create_checkout(
        self,
        *,
        order_id: uuid.UUID,
        title: str,
        amount_cents: int,
        fee_cents: int,
        currency: str,
        seller_account: str,
        buyer_email: str,
        success_url: str,
        cancel_url: str,
    ) -> Checkout:
        session = self._post(
            "/checkout/sessions",
            {
                "mode": "payment",
                "client_reference_id": str(order_id),
                "customer_email": buyer_email,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "line_items[0][quantity]": "1",
                "line_items[0][price_data][currency]": currency.lower(),
                "line_items[0][price_data][unit_amount]": str(amount_cents),
                "line_items[0][price_data][product_data][name]": title[:200],
                "payment_intent_data[application_fee_amount]": str(fee_cents),
                "payment_intent_data[transfer_data][destination]": seller_account,
                "payment_intent_data[metadata][order_id]": str(order_id),
                "metadata[order_id]": str(order_id),
            },
        )
        return Checkout(session_id=str(session["id"]), url=str(session["url"]))

    def parse_event(self, payload: bytes, signature: str) -> PaymentEvent | None:
        """The event, once its signature is verified; None for kinds that don't matter here.
        Raises InvalidRequestError when the signature is missing, wrong or too old."""
        verify_stripe_signature(payload, signature, self._webhook_secret)
        event = json.loads(payload)
        kind, obj = event.get("type"), event.get("data", {}).get("object", {})
        if kind == "checkout.session.completed" and obj.get("payment_status") == "paid":
            return PaymentEvent(
                "paid", session_id=obj.get("id"), payment_id=obj.get("payment_intent")
            )
        if kind == "checkout.session.async_payment_succeeded":
            return PaymentEvent(
                "paid", session_id=obj.get("id"), payment_id=obj.get("payment_intent")
            )
        if kind in ("checkout.session.expired", "checkout.session.async_payment_failed"):
            return PaymentEvent("expired", session_id=obj.get("id"))
        if kind == "charge.refunded" and obj.get("refunded"):
            return PaymentEvent("refunded", payment_id=obj.get("payment_intent"))
        if kind == "account.updated":
            return PaymentEvent(
                "seller_updated",
                account_id=obj.get("id"),
                seller_ready=bool(obj.get("charges_enabled"))
                and bool(obj.get("details_submitted")),
            )
        return None


def verify_stripe_signature(
    payload: bytes, header: str, secret: str, now: float | None = None
) -> None:
    """Stripe-Signature: "t=<unix time>,v1=<hex hmac-sha256 of 't.payload'>[,v1=…]"."""
    parts: dict[str, list[str]] = {}
    for piece in header.split(","):
        key, _, value = piece.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, IndexError, ValueError):
        raise InvalidRequestError("Invalid signature.") from None
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, given) for given in parts.get("v1", [])):
        raise InvalidRequestError("Invalid signature.")
    if abs((now if now is not None else time.time()) - timestamp) > SIGNATURE_TOLERANCE:
        raise InvalidRequestError("Invalid signature.")


def build_gateway(settings: Settings) -> PaymentGateway | None:
    if settings.payments_provider == "stripe":
        return StripeGateway(
            settings.stripe_secret_key.get_secret_value(),
            settings.stripe_webhook_secret.get_secret_value(),
        )
    return None


@lru_cache
def _configured_gateway() -> PaymentGateway | None:
    return build_gateway(get_settings())


def get_payment_gateway() -> PaymentGateway | None:
    """FastAPI dependency (tests override it with a fake). None: payments are off."""
    return _configured_gateway()


def _need(gateway: PaymentGateway | None) -> PaymentGateway:
    if gateway is None:
        raise ConflictError(
            "Paid courses aren't available on this server.",
            details={"reason": "payments_unavailable"},
        )
    return gateway


def fee_for(amount_cents: int, percent: int) -> int:
    return amount_cents * percent // 100


# --- The author's side ---


def payout_status(user: User, gateway: PaymentGateway | None) -> PayoutStatus:
    settings = get_settings()
    return PayoutStatus(
        enabled=gateway is not None,
        account=user.payout_account_id is not None,
        ready=gateway is not None and user.payout_ready,
        fee_percent=settings.platform_fee_percent,
        price_min_cents=settings.price_min_cents,
        price_max_cents=settings.price_max_cents,
    )


def refresh_payout(db: Session, user: User, gateway: PaymentGateway | None) -> PayoutStatus:
    """Asks the provider whether the author's account can take payments now (they come back
    from the onboarding pages before the webhook may have arrived)."""
    if gateway is not None and user.payout_account_id and not user.payout_ready:
        user.payout_ready = gateway.seller_ready(user.payout_account_id)
        db.commit()
    return payout_status(user, gateway)


def start_onboarding(db: Session, user: User, gateway: PaymentGateway | None) -> str:
    """The provider's page where the author enters who they are and where to be paid."""
    gateway = _need(gateway)
    if user.payout_account_id is None:
        user.payout_account_id = gateway.create_seller_account(user.email)
        user.payout_ready = False
        db.commit()
    return_url = f"{get_settings().public_app_url.rstrip('/')}/marketplace/sales?payments=return"
    return gateway.onboarding_link(user.payout_account_id, return_url)


def check_price(user: User, price_cents: int, gateway: PaymentGateway | None) -> None:
    """A price the author may publish with."""
    if price_cents == 0:
        return
    settings = get_settings()
    if gateway is None:
        raise ConflictError(
            "Paid courses aren't available on this server: publish it for free.",
            details={"reason": "payments_unavailable"},
        )
    if not settings.price_min_cents <= price_cents <= settings.price_max_cents:
        raise InvalidRequestError(
            f"The price must be between {settings.price_min_cents / 100:.2f} and "
            f"{settings.price_max_cents / 100:.2f}, or free."
        )
    if not user.payout_ready:
        raise ConflictError(
            "Set up payments first, so buyers can pay you.",
            details={"reason": "payout_not_ready"},
        )


# --- The buyer's side ---


def checkout(
    db: Session, buyer: User, listing_id: uuid.UUID, gateway: PaymentGateway | None
) -> str:
    """Starts a purchase and returns the payment page's address."""
    gateway = _need(gateway)
    listing = db.get(MarketplaceListing, listing_id)
    if listing is None or listing.status != "PUBLISHED":
        raise NotFoundError("Listing not found")
    if listing.author_id == buyer.id:
        raise ConflictError("This is your own course.", details={"reason": "own_listing"})
    if listing.price_cents <= 0:
        raise ConflictError("This course is free.", details={"reason": "free_listing"})
    has_access = db.scalar(
        select(MarketplaceAcquisition.id).where(
            MarketplaceAcquisition.listing_id == listing.id,
            MarketplaceAcquisition.user_id == buyer.id,
        )
    )
    if has_access is not None:
        raise ConflictError("You already have this course.", details={"reason": "already_acquired"})
    seller = db.get(User, listing.author_id)
    if seller is None or not seller.payout_ready or not seller.payout_account_id:
        raise ConflictError(
            "The author can't take payments right now.", details={"reason": "seller_not_ready"}
        )
    settings = get_settings()
    order = MarketplaceOrder(
        id=uuid.uuid4(),
        listing_id=listing.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        amount_cents=listing.price_cents,
        fee_cents=fee_for(listing.price_cents, settings.platform_fee_percent),
        currency=listing.currency,
        provider=gateway.name,
    )
    db.add(order)
    db.flush()
    base = settings.public_app_url.rstrip("/")
    session = gateway.create_checkout(
        order_id=order.id,
        title=listing.title,
        amount_cents=order.amount_cents,
        fee_cents=order.fee_cents,
        currency=order.currency,
        seller_account=seller.payout_account_id,
        buyer_email=buyer.email,
        success_url=f"{base}/marketplace/{listing.id}?order={order.id}",
        cancel_url=f"{base}/marketplace/{listing.id}?cancelled=1",
    )
    order.provider_session_id = session.session_id
    db.commit()
    return session.url


def order_status(db: Session, buyer: User, order_id: uuid.UUID) -> str:
    order = db.get(MarketplaceOrder, order_id)
    if order is None or order.buyer_id != buyer.id:
        raise NotFoundError("Order not found")
    return order.status


# --- What the provider tells us ---


def apply_event(db: Session, event: PaymentEvent) -> tuple[MarketplaceOrder, str] | None:
    """Applies a verified event. Returns the order with "paid" when it has just been paid (the
    caller gives access and commits) or "refunded" (the caller removes access); otherwise
    None. Safe to receive twice."""
    if event.kind == "seller_updated" and event.account_id:
        seller = db.scalar(select(User).where(User.payout_account_id == event.account_id))
        if seller is not None:
            seller.payout_ready = event.seller_ready
            db.commit()
        return None
    order: MarketplaceOrder | None = None
    if event.session_id:
        order = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.provider_session_id == event.session_id)
        )
    elif event.payment_id:
        order = db.scalar(
            select(MarketplaceOrder).where(MarketplaceOrder.provider_payment_id == event.payment_id)
        )
    if order is None:
        return None
    if event.kind == "paid" and order.status == PENDING:
        order.status = PAID
        order.paid_at = utc_now()
        order.provider_payment_id = event.payment_id
        return order, "paid"
    if event.kind == "refunded" and order.status == PAID:
        order.status = REFUNDED
        order.refunded_at = utc_now()
        return order, "refunded"
    if event.kind == "expired" and order.status == PENDING:
        order.status = EXPIRED
        db.commit()
    return None


def notify_sale(db: Session, order: MarketplaceOrder, listing: MarketplaceListing) -> None:
    if order.seller_id is None:
        return
    notifications.notify(
        db,
        order.seller_id,
        "course_sold",
        actor_id=order.buyer_id,
        data={
            "listing_id": str(listing.id),
            "title": listing.title,
            "amount_cents": order.amount_cents - order.fee_cents,
            "currency": order.currency,
        },
        link="/marketplace/sales",
    )


def sales(db: Session, seller: User) -> Sales:
    rows = db.execute(
        select(MarketplaceOrder, MarketplaceListing.title)
        .join(MarketplaceListing, MarketplaceListing.id == MarketplaceOrder.listing_id)
        .where(
            MarketplaceOrder.seller_id == seller.id,
            MarketplaceOrder.status.in_((PAID, REFUNDED)),
        )
        .order_by(MarketplaceOrder.paid_at.desc())
        .limit(200)
    ).all()
    totals = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(MarketplaceOrder.amount_cents), 0),
            func.coalesce(func.sum(MarketplaceOrder.fee_cents), 0),
        ).where(MarketplaceOrder.seller_id == seller.id, MarketplaceOrder.status == PAID)
    ).one()
    return Sales(
        count=int(totals[0]),
        gross_cents=int(totals[1]),
        net_cents=int(totals[1]) - int(totals[2]),
        currency="EUR",
        items=[
            Sale(
                id=order.id,
                listing_id=order.listing_id,
                title=title,
                amount_cents=order.amount_cents,
                net_cents=order.amount_cents - order.fee_cents,
                currency=order.currency,
                paid_at=order.paid_at or order.created_at,
                refunded=order.status == REFUNDED,
            )
            for order, title in rows
        ],
    )
