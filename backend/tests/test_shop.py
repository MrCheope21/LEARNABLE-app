"""The shop around the marketplace: prices and payments, reviews with stars, update notes and
announcements to the people who have a course."""

import hashlib
import hmac
import json
import time
import uuid

import pytest
from test_marketplace import API, PUBLISH, acquire, publish
from test_marketplace import author as author
from test_review import item

from app.core.config import get_settings
from app.core.errors import InvalidRequestError
from app.main import app
from app.models.marketplace import MarketplaceOrder
from app.models.user import User
from app.services import payments
from app.services.payments import Checkout, PaymentEvent, get_payment_gateway


class FakeGateway:
    """Stands in for Stripe: remembers what it was asked and lets the test send events."""

    name = "fake"

    def __init__(self):
        self.ready = False
        self.checkouts = []
        self.refunds = []

    def refund(self, payment_id):
        self.refunds.append(payment_id)

    def create_seller_account(self, email):
        return "acct_test_1"

    def onboarding_link(self, account_id, return_url):
        return f"https://pay.example/onboard/{account_id}"

    def seller_ready(self, account_id):
        return self.ready

    def create_checkout(self, **kwargs):
        self.checkouts.append(kwargs)
        return Checkout(session_id=f"cs_{len(self.checkouts)}", url="https://pay.example/checkout")

    def parse_event(self, payload, signature):
        if signature != "good":
            raise InvalidRequestError("Invalid signature.")
        return PaymentEvent(**json.loads(payload))


@pytest.fixture
def gateway(client):
    fake = FakeGateway()
    app.dependency_overrides[get_payment_gateway] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_payment_gateway, None)


@pytest.fixture
def outbox(client):
    from app.email.sender import get_email_sender

    class Box:
        def __init__(self):
            self.sent = []

        def send(self, to, subject, body):
            self.sent.append((to, subject, body))

    box = Box()
    app.dependency_overrides[get_email_sender] = lambda: box
    yield box
    app.dependency_overrides.pop(get_email_sender, None)


def webhook(client, signature="good", **event):
    return client.post(
        f"{API}/payments/stripe/webhook",
        content=json.dumps(event),
        headers={"Stripe-Signature": signature},
    )


def onboard(client, headers, gateway):
    """The author sets up payments and the provider says the account is ready."""
    link = client.post(f"{API}/payments/payout/onboarding", headers=headers)
    assert link.status_code == 200, link.text
    gateway.ready = True
    status = client.get(f"{API}/payments/payout", headers=headers).json()
    assert status["ready"] is True
    return link.json()["url"]


def notes(client, headers):
    return client.get(f"{API}/notifications", headers=headers).json()["items"]


# --- Prices ---


def test_without_payments_every_course_is_free_and_a_price_is_refused(client, author):
    status = client.get(f"{API}/payments/payout", headers=author["headers"]).json()
    assert (status["enabled"], status["ready"]) == (False, False)
    refused = publish(client, author, {**PUBLISH, "price_cents": 990})
    assert (refused.status_code, refused.json()["details"]["reason"]) == (
        409,
        "payments_unavailable",
    )
    assert (
        client.post(f"{API}/payments/payout/onboarding", headers=author["headers"]).status_code
        == 409
    )
    free = publish(client, author).json()
    assert (free["price_cents"], free["rating_count"], free["rating_average"]) == (0, 0, None)


def test_a_price_needs_the_author_to_set_up_payments_first(client, author, gateway):
    refused = publish(client, author, {**PUBLISH, "price_cents": 990})
    assert refused.json()["details"]["reason"] == "payout_not_ready"

    assert onboard(client, author["headers"], gateway) == "https://pay.example/onboard/acct_test_1"
    # Too cheap or too dear.
    for cents in (10, 99_999_00):
        assert publish(client, author, {**PUBLISH, "price_cents": cents}).status_code == 422
    listing = publish(client, author, {**PUBLISH, "price_cents": 990}).json()
    assert (listing["price_cents"], listing["currency"]) == (990, "EUR")


def test_buying_gives_access_only_when_the_provider_confirms(
    client, auth_headers, author, gateway, db_session
):
    onboard(client, author["headers"], gateway)
    listing = publish(client, author, {**PUBLISH, "price_cents": 1000}).json()
    buyer = auth_headers("buyer@example.com")

    # A paid course can't simply be added.
    blocked = acquire(client, buyer, listing["id"])
    assert (blocked.status_code, blocked.json()["details"]["reason"]) == (409, "payment_required")
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert (shown["can_buy"], shown["has_access"]) == (True, False)
    # The author doesn't buy their own course.
    own = client.post(
        f"{API}/marketplace/listings/{listing['id']}/checkout", headers=author["headers"]
    )
    assert own.status_code == 409

    started = client.post(f"{API}/marketplace/listings/{listing['id']}/checkout", headers=buyer)
    assert started.json() == {"url": "https://pay.example/checkout"}
    [asked] = gateway.checkouts
    fee = 1000 * get_settings().platform_fee_percent // 100
    assert (asked["amount_cents"], asked["fee_cents"], asked["seller_account"]) == (
        1000,
        fee,
        "acct_test_1",
    )
    order = db_session.query(MarketplaceOrder).one()
    assert order.status == "PENDING"
    pending = client.get(f"{API}/marketplace/orders/{order.id}", headers=buyer).json()
    assert pending == {"status": "PENDING", "course_id": None}
    # Coming back from the payment page proves nothing: still no access.
    assert acquire(client, buyer, listing["id"]).status_code == 409

    # A forged call is refused; the real one gives access, once.
    assert webhook(client, signature="bad", kind="paid", session_id="cs_1").status_code == 422
    assert acquire(client, buyer, listing["id"]).status_code == 409
    for _ in range(2):
        confirmed = webhook(client, kind="paid", session_id="cs_1", payment_id="pi_1")
        assert confirmed.status_code == 204
    paid = client.get(f"{API}/marketplace/orders/{order.id}", headers=buyer).json()
    assert paid["status"] == "PAID"
    assert paid["course_id"]
    courses = client.get(f"{API}/courses", headers=buyer).json()
    assert [c["title"] for c in courses] == [PUBLISH["title"]]
    # Another person can't read the order.
    assert (
        client.get(
            f"{API}/marketplace/orders/{order.id}", headers=auth_headers("x@example.com")
        ).status_code
        == 404
    )

    # The author is told and sees the sale, net of the platform's fee.
    [sold] = [n for n in notes(client, author["headers"]) if n["kind"] == "course_sold"]
    assert sold["data"]["amount_cents"] == 1000 - fee
    sales = client.get(f"{API}/marketplace/sales", headers=author["headers"]).json()
    assert (sales["count"], sales["gross_cents"], sales["net_cents"]) == (1, 1000, 1000 - fee)
    assert client.get(f"{API}/marketplace/sales", headers=buyer).json()["count"] == 0
    # Buying twice isn't possible.
    again = client.post(f"{API}/marketplace/listings/{listing['id']}/checkout", headers=buyer)
    assert again.json()["details"]["reason"] == "already_acquired"


def test_a_refund_takes_the_course_and_the_review_back(
    client, auth_headers, author, gateway, db_session
):
    onboard(client, author["headers"], gateway)
    listing = publish(client, author, {**PUBLISH, "price_cents": 500}).json()
    buyer = auth_headers("buyer@example.com")
    client.post(f"{API}/marketplace/listings/{listing['id']}/checkout", headers=buyer)
    webhook(client, kind="paid", session_id="cs_1", payment_id="pi_9")
    client.put(
        f"{API}/marketplace/listings/{listing['id']}/review", json={"rating": 2}, headers=buyer
    )

    assert webhook(client, kind="refunded", payment_id="pi_9").status_code == 204
    assert client.get(f"{API}/courses", headers=buyer).json() == []
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert (shown["has_access"], shown["rating_count"], shown["acquisition_count"]) == (False, 0, 0)
    sales = client.get(f"{API}/marketplace/sales", headers=author["headers"]).json()
    assert (sales["count"], sales["items"][0]["refunded"]) == (0, True)


def test_the_provider_can_say_the_seller_is_no_longer_ready(
    client, auth_headers, author, gateway, db_session
):
    onboard(client, author["headers"], gateway)
    listing = publish(client, author, {**PUBLISH, "price_cents": 500}).json()
    webhook(client, kind="seller_updated", account_id="acct_test_1", seller_ready=False)
    buyer = auth_headers("buyer@example.com")
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert shown["can_buy"] is False
    refused = client.post(f"{API}/marketplace/listings/{listing['id']}/checkout", headers=buyer)
    assert refused.json()["details"]["reason"] == "seller_not_ready"
    assert db_session.query(User).filter(User.payout_account_id == "acct_test_1").one()


def test_stripe_signatures_are_verified():
    secret, payload = "whsec_test", b'{"type":"x"}'
    now = int(time.time())

    def header(at, key=secret):
        mac = hmac.new(key.encode(), f"{at}.".encode() + payload, hashlib.sha256).hexdigest()
        return f"t={at},v1={mac}"

    payments.verify_stripe_signature(payload, header(now), secret)
    for bad in (header(now, "other"), header(now - 3600), "garbage", ""):
        with pytest.raises(InvalidRequestError):
            payments.verify_stripe_signature(payload, bad, secret)
    with pytest.raises(InvalidRequestError):
        payments.verify_stripe_signature(b'{"type":"y"}', header(now), secret)


def test_stripe_events_are_read():
    stripe = payments.StripeGateway("sk_test", "whsec_test")

    def event(kind, obj):
        payload = json.dumps({"type": kind, "data": {"object": obj}}).encode()
        at = int(time.time())
        mac = hmac.new(b"whsec_test", f"{at}.".encode() + payload, hashlib.sha256).hexdigest()
        return stripe.parse_event(payload, f"t={at},v1={mac}")

    paid = event(
        "checkout.session.completed",
        {"id": "cs_1", "payment_status": "paid", "payment_intent": "pi_1"},
    )
    assert (paid.kind, paid.session_id, paid.payment_id) == ("paid", "cs_1", "pi_1")
    # Completed but not paid yet (a delayed payment method): nothing happens.
    assert event("checkout.session.completed", {"id": "cs_1", "payment_status": "unpaid"}) is None
    assert event("checkout.session.expired", {"id": "cs_2"}).kind == "expired"
    assert event("charge.refunded", {"refunded": True, "payment_intent": "pi_1"}).kind == "refunded"
    seller = event(
        "account.updated", {"id": "acct_1", "charges_enabled": True, "details_submitted": True}
    )
    assert (seller.kind, seller.seller_ready) == ("seller_updated", True)
    assert event("customer.created", {}) is None


def test_the_webhook_does_not_exist_without_payments(client):
    assert webhook(client, kind="paid", session_id="cs_1").status_code == 404


def test_browsing_filters_by_price(client, auth_headers, author, gateway):
    onboard(client, author["headers"], gateway)
    publish(client, author, {**PUBLISH, "price_cents": 700})
    viewer = auth_headers("viewer@example.com")

    def titles(**params):
        found = client.get(f"{API}/marketplace/listings", params=params, headers=viewer).json()
        return [x["title"] for x in found]

    assert titles(price="paid") == [PUBLISH["title"]]
    assert titles(price="free") == []


# --- Reviews ---


def review(client, headers, listing_id, **body):
    return client.put(f"{API}/marketplace/listings/{listing_id}/review", json=body, headers=headers)


def test_only_people_who_have_the_course_review_it_once(client, auth_headers, author):
    listing = publish(client, author).json()
    stranger = auth_headers("stranger@example.com")
    assert review(client, stranger, listing["id"], rating=5).json()["details"]["reason"] == (
        "no_access"
    )
    assert review(client, author["headers"], listing["id"], rating=5).status_code == 409

    buyer = auth_headers("buyer@example.com")
    client.patch(f"{API}/auth/me", json={"display_name": "Giulia"}, headers=buyer)
    acquire(client, buyer, listing["id"])
    for bad in (0, 6):
        assert review(client, buyer, listing["id"], rating=bad).status_code == 422
    written = review(client, buyer, listing["id"], rating=4, comment="  Chiaro e completo. ")
    assert written.status_code == 200, written.text
    data = written.json()
    assert (data["count"], data["average"], data["distribution"]) == (1, 4.0, [0, 0, 0, 1, 0])
    assert (data["mine"]["comment"], data["mine"]["author"], data["can_review"]) == (
        "Chiaro e completo.",
        "Giulia",
        True,
    )
    # Writing again edits it: still one review.
    edited = review(client, buyer, listing["id"], rating=2, comment="Ci ho ripensato.").json()
    assert (edited["count"], edited["average"]) == (1, 2.0)

    second = auth_headers("second@example.com")
    acquire(client, second, listing["id"])
    review(client, second, listing["id"], rating=5)
    seen = client.get(f"{API}/marketplace/listings/{listing['id']}/reviews", headers=stranger)
    body = seen.json()
    assert (body["count"], body["average"], body["mine"], body["can_review"]) == (
        2,
        3.5,
        None,
        False,
    )
    assert "buyer@example.com" not in seen.text
    card = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=stranger).json()
    assert (card["rating_count"], card["rating_average"]) == (2, 3.5)

    # The author is told once per reviewer.
    kinds = [n["kind"] for n in notes(client, author["headers"])]
    assert kinds.count("course_review") == 2

    assert (
        client.delete(
            f"{API}/marketplace/listings/{listing['id']}/review", headers=buyer
        ).status_code
        == 204
    )
    after = client.get(f"{API}/marketplace/listings/{listing['id']}/reviews", headers=buyer).json()
    assert (after["count"], after["average"], after["mine"]) == (1, 5.0, None)


def test_the_author_answers_a_review_and_an_admin_can_remove_one(
    client, auth_headers, author, db_session
):
    listing = publish(client, author).json()
    buyer = auth_headers("buyer@example.com")
    acquire(client, buyer, listing["id"])
    mine = review(client, buyer, listing["id"], rating=3, comment="Mancano esempi.").json()["mine"]

    # Only the course's author answers.
    nosy = client.put(
        f"{API}/marketplace/reviews/{mine['id']}/reply", json={"reply": "Io!"}, headers=buyer
    )
    assert nosy.status_code == 404
    answered = client.put(
        f"{API}/marketplace/reviews/{mine['id']}/reply",
        json={"reply": "Li aggiungo nella prossima versione."},
        headers=author["headers"],
    )
    assert answered.status_code == 204
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}/reviews", headers=buyer).json()
    assert shown["items"][0]["reply"] == "Li aggiungo nella prossima versione."
    assert [n["kind"] for n in notes(client, buyer)] == ["review_reply"]

    # Moderation is for administrators.
    assert client.delete(f"{API}/admin/reviews/{mine['id']}", headers=buyer).status_code == 403
    admin = auth_headers("boss@example.com")
    boss = db_session.query(User).filter(User.email == "boss@example.com").one()
    boss.is_admin = True
    db_session.commit()
    assert client.delete(f"{API}/admin/reviews/{mine['id']}", headers=admin).status_code == 204
    gone = client.get(f"{API}/marketplace/listings/{listing['id']}/reviews", headers=buyer).json()
    assert (gone["count"], gone["items"]) == (0, [])


def test_best_rated_sorts_by_stars_with_unreviewed_courses_last(client, auth_headers, author):
    first = publish(client, author).json()
    other = auth_headers("other-author@example.com")
    course = client.post(f"{API}/courses", json={"title": "Altro", "language": "it"}, headers=other)
    chapter = client.post(
        f"{API}/courses/{course.json()['id']}/chapters", json={"title": "C"}, headers=other
    ).json()
    topic = client.post(
        f"{API}/chapters/{chapter['id']}/topics", json={"title": "T"}, headers=other
    ).json()
    from test_review import concept

    item(client, other, concept(client, other, topic["id"], active=False)["id"])
    second = client.post(
        f"{API}/courses/{course.json()['id']}/marketplace/publish",
        json={**PUBLISH, "title": "Senza recensioni"},
        headers=other,
    ).json()
    buyer = auth_headers("buyer@example.com")
    acquire(client, buyer, first["id"])
    review(client, buyer, first["id"], rating=3)
    found = client.get(
        f"{API}/marketplace/listings", params={"sort": "best_rated"}, headers=buyer
    ).json()
    assert [x["id"] for x in found] == [first["id"], second["id"]]


# --- Update notes and announcements ---


def test_a_new_version_tells_everyone_who_has_the_course(
    client, auth_headers, author, outbox, monkeypatch
):
    monkeypatch.setattr(get_settings(), "email_backend", "smtp")
    listing = publish(client, author).json()
    buyer = auth_headers("buyer@example.com")
    quiet = auth_headers("quiet@example.com")
    client.patch(f"{API}/auth/me", json={"email_updates": False}, headers=quiet)
    for headers in (buyer, quiet):
        acquire(client, headers, listing["id"])
    # The first publication told nobody.
    assert notes(client, buyer) == []
    assert outbox.sent == []

    note = "Aggiunte 20 domande sul fallimento. Le troverai come nuove, da studiare."
    updated = publish(client, author, {**PUBLISH, "update_note": note}).json()
    assert updated["version"] == 2
    for headers in (buyer, quiet):
        [told] = notes(client, headers)
        assert (told["kind"], told["actor"], told["link"]) == (
            "course_update",
            "Prof. Rossi",
            f"/marketplace/{listing['id']}",
        )
        assert (told["data"]["version"], told["data"]["note"]) == (2, note)
    # The note is the listing's "What's new", and was emailed to who takes such emails.
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert [(u["version"], u["note"]) for u in shown["updates"]] == [(2, note)]
    assert [to for to, _, _ in outbox.sent] == ["buyer@example.com"]
    assert note in outbox.sent[0][2]
    # The author isn't told about their own update.
    assert [n for n in notes(client, author["headers"]) if n["kind"] == "course_update"] == []

    # Without a note: still a notification, no email, nothing new in "What's new".
    publish(client, author)
    assert [n["data"]["version"] for n in notes(client, buyer)] == [3, 2]
    assert len(outbox.sent) == 1
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert len(shown["updates"]) == 1


def test_the_author_announces_to_everyone_who_has_the_course(client, auth_headers, author):
    course_id = author["course"]["id"]
    body = {"message": "Venerdì aggiorno il capitolo 2: finitelo prima se potete."}
    # Nothing to announce to before publishing.
    early = client.post(
        f"{API}/courses/{course_id}/marketplace/announce", json=body, headers=author["headers"]
    )
    assert early.status_code == 409
    listing = publish(client, author).json()
    buyer = auth_headers("buyer@example.com")
    acquire(client, buyer, listing["id"])

    sent = client.post(
        f"{API}/courses/{course_id}/marketplace/announce", json=body, headers=author["headers"]
    )
    assert sent.json() == {"recipients": 1}
    [told] = notes(client, buyer)
    assert (told["kind"], told["data"]["message"]) == ("course_announcement", body["message"])
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert [(u["version"], u["note"]) for u in shown["updates"]] == [(None, body["message"])]
    # Only the course's owner announces.
    assert (
        client.post(
            f"{API}/courses/{course_id}/marketplace/announce", json=body, headers=buyer
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/courses/{uuid.uuid4()}/marketplace/announce",
            json=body,
            headers=author["headers"],
        ).status_code
        == 404
    )


def test_free_sample_refund_from_the_app_and_discount_codes(
    client, auth_headers, author, gateway, db_session
):
    onboard(client, author["headers"], gateway)
    listing = publish(client, author, {**PUBLISH, "price_cents": 1000, "preview_count": 1}).json()
    buyer = auth_headers("buyer@example.com")
    other = auth_headers("other@example.com")
    course = author["course"]["id"]

    # The free sample: the first question with its answer, and no more than the author chose.
    shown = client.get(f"{API}/marketplace/listings/{listing['id']}", headers=buyer).json()
    assert len(shown["preview"]) == 1
    assert shown["preview"][0]["question"]
    assert shown["preview"][0]["answer"]

    # A code from the author: 40% off, usable once.
    made = client.post(
        f"{API}/courses/{course}/marketplace/discounts",
        json={"code": "amici40", "percent_off": 40, "max_uses": 1},
        headers=author["headers"],
    )
    assert made.status_code == 201
    assert made.json()["code"] == "AMICI40"
    again = client.post(
        f"{API}/courses/{course}/marketplace/discounts",
        json={"code": "AMICI40", "percent_off": 10},
        headers=author["headers"],
    )
    assert again.status_code == 409
    # Only the author manages the codes of a course.
    assert (
        client.get(f"{API}/courses/{course}/marketplace/discounts", headers=buyer).status_code
        == 404
    )
    quote = client.get(
        f"{API}/marketplace/listings/{listing['id']}/discount",
        params={"code": "amici40"},
        headers=buyer,
    ).json()
    assert (quote["percent_off"], quote["price_cents"]) == (40, 600)
    wrong = client.post(
        f"{API}/marketplace/listings/{listing['id']}/checkout", json={"code": "NOPE"}, headers=buyer
    )
    assert wrong.status_code == 422
    assert wrong.json()["details"]["reason"] == "invalid_code"

    client.post(
        f"{API}/marketplace/listings/{listing['id']}/checkout",
        json={"code": "Amici40"},
        headers=buyer,
    )
    assert gateway.checkouts[-1]["amount_cents"] == 600
    assert gateway.checkouts[-1]["fee_cents"] == 60
    webhook(client, kind="paid", session_id="cs_1", payment_id="pi_1")
    codes = client.get(f"{API}/courses/{course}/marketplace/discounts", headers=author["headers"])
    assert codes.json()[0]["used_count"] == 1
    # Used up: the next person pays the full price or gets told.
    spent = client.post(
        f"{API}/marketplace/listings/{listing['id']}/checkout",
        json={"code": "AMICI40"},
        headers=other,
    )
    assert spent.status_code == 422

    # The author refunds the sale from the app.
    sale = client.get(f"{API}/marketplace/sales", headers=author["headers"]).json()["items"][0]
    assert (sale["amount_cents"], sale["discount_code"]) == (600, "AMICI40")
    assert (
        client.post(f"{API}/marketplace/orders/{sale['id']}/refund", headers=other).status_code
        == 404
    )
    done = client.post(f"{API}/marketplace/orders/{sale['id']}/refund", headers=author["headers"])
    assert done.status_code == 204
    assert gateway.refunds == ["pi_1"]
    assert client.get(f"{API}/courses", headers=buyer).json() == []
    told = client.get(f"{API}/notifications", headers=buyer).json()["items"]
    assert told[0]["kind"] == "order_refunded"
    assert told[0]["data"]["amount_cents"] == 600
    twice = client.post(f"{API}/marketplace/orders/{sale['id']}/refund", headers=author["headers"])
    assert twice.status_code == 409
    # Stripe's own notice of the same refund changes nothing more.
    assert webhook(client, kind="refunded", payment_id="pi_1").status_code == 204
    removed = client.delete(
        f"{API}/courses/{course}/marketplace/discounts/{made.json()['id']}",
        headers=author["headers"],
    )
    assert removed.status_code == 204
