"""Payments for paid courses: the author's payout setup, the buyer's checkout, the provider's
webhook (services/payments.py)."""

import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.errors import InvalidRequestError, NotFoundError
from app.core.rate_limit import per_user
from app.db.session import get_db
from app.models.marketplace import (
    MarketplaceAcquisition,
    MarketplaceListing,
    MarketplaceOrder,
)
from app.models.user import User
from app.schemas.marketplace import (
    CheckoutStart,
    DiscountCreate,
    DiscountQuote,
    DiscountRead,
    OrderStatus,
    PayoutStatus,
    Redirect,
    Sales,
)
from app.services import marketplace, payments
from app.services.documents.service import delete_course_files
from app.services.payments import PaymentGateway, get_payment_gateway
from app.storage.documents import DocumentStorage, get_document_storage

router = APIRouter(tags=["payments"])

CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
Gateway = Depends(get_payment_gateway)


@router.get("/payments/payout", response_model=PayoutStatus)
def payout(
    db: Session = DB, user: User = CurrentUser, gateway: PaymentGateway | None = Gateway
) -> PayoutStatus:
    """Whether the viewer can sell paid courses, checked with the provider when pending."""
    return payments.refresh_payout(db, user, gateway)


@router.post(
    "/payments/payout/onboarding",
    response_model=Redirect,
    dependencies=[Depends(per_user("payout_onboarding", 20, 3600))],
)
def onboarding(
    db: Session = DB, user: User = CurrentUser, gateway: PaymentGateway | None = Gateway
) -> Redirect:
    return Redirect(url=payments.start_onboarding(db, user, gateway))


@router.post(
    "/marketplace/listings/{listing_id}/checkout",
    response_model=Redirect,
    dependencies=[Depends(per_user("marketplace_checkout", 20, 3600))],
)
def checkout(
    listing_id: uuid.UUID,
    payload: CheckoutStart | None = None,
    db: Session = DB,
    user: User = CurrentUser,
    gateway: PaymentGateway | None = Gateway,
) -> Redirect:
    """Starts buying a paid course: the address of the payment page."""
    code = payload.code if payload else ""
    return Redirect(url=payments.checkout(db, user, listing_id, gateway, code))


@router.get("/marketplace/listings/{listing_id}/discount", response_model=DiscountQuote)
def discount_quote(
    listing_id: uuid.UUID,
    code: str = Query(max_length=40),
    db: Session = DB,
    _user: User = CurrentUser,
    _limit: None = Depends(per_user("discount_quote", 60, 3600)),
) -> DiscountQuote:
    """What a discount code makes the price (422 `invalid_code` when it can't be used)."""
    return payments.quote(db, listing_id, code)


@router.get("/courses/{course_id}/marketplace/discounts", response_model=list[DiscountRead])
def list_discounts(
    course_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> list[DiscountRead]:
    return payments.discounts(db, user, course_id)


@router.post(
    "/courses/{course_id}/marketplace/discounts",
    response_model=DiscountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_discount(
    course_id: uuid.UUID, payload: DiscountCreate, db: Session = DB, user: User = CurrentUser
) -> DiscountRead:
    return payments.create_discount(db, user, course_id, payload)


@router.delete(
    "/courses/{course_id}/marketplace/discounts/{discount_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_discount(
    course_id: uuid.UUID, discount_id: uuid.UUID, db: Session = DB, user: User = CurrentUser
) -> None:
    payments.delete_discount(db, user, course_id, discount_id)


@router.post(
    "/marketplace/orders/{order_id}/refund",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(per_user("marketplace_refund", 30, 3600))],
)
def refund_order(
    order_id: uuid.UUID,
    db: Session = DB,
    user: User = CurrentUser,
    gateway: PaymentGateway | None = Gateway,
    storage: DocumentStorage = Depends(get_document_storage),
) -> None:
    """The author gives the buyer their money back; the course leaves the buyer's courses."""
    refunded = payments.refund(db, user, order_id, gateway)
    listing = db.get(MarketplaceListing, refunded.listing_id)
    keys = marketplace.revoke(db, refunded.buyer_id, listing) if listing else []
    db.commit()
    delete_course_files(storage, keys)


@router.get("/marketplace/orders/{order_id}", response_model=OrderStatus)
def order(order_id: uuid.UUID, db: Session = DB, user: User = CurrentUser) -> OrderStatus:
    """Polled by the buyer's browser after the payment page, until the provider confirmed."""
    row = db.get(MarketplaceOrder, order_id)
    if row is None or row.buyer_id != user.id:
        raise NotFoundError("Order not found")
    course_id = db.scalar(
        select(MarketplaceAcquisition.course_id).where(
            MarketplaceAcquisition.listing_id == row.listing_id,
            MarketplaceAcquisition.user_id == user.id,
        )
    )
    return OrderStatus(status=row.status, course_id=course_id)


@router.get("/marketplace/sales", response_model=Sales)
def sales(db: Session = DB, user: User = CurrentUser) -> Sales:
    return payments.sales(db, user)


@router.post("/payments/stripe/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default=""),
    db: Session = DB,
    gateway: PaymentGateway | None = Gateway,
    storage: DocumentStorage = Depends(get_document_storage),
) -> None:
    """Called by Stripe, not by a browser: no session, the signature is the proof."""
    if gateway is None:
        raise NotFoundError("Not found")
    payload = await request.body()
    if len(payload) > 512_000:
        raise InvalidRequestError("Payload too large.")
    event = gateway.parse_event(payload, stripe_signature)
    if event is None:
        return
    applied = payments.apply_event(db, event)
    if applied is None:
        return
    paid_order, what = applied
    listing = db.get(MarketplaceListing, paid_order.listing_id)
    if listing is None:
        db.commit()
        return
    if what == "paid":
        marketplace.grant(
            db, storage, paid_order.buyer_id, listing, price_cents=paid_order.amount_cents
        )
        payments.notify_sale(db, paid_order, listing)
        db.commit()
    else:
        keys = marketplace.revoke(db, paid_order.buyer_id, listing)
        db.commit()
        delete_course_files(storage, keys)
