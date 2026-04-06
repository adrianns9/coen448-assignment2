import os
import subprocess
import time
import uuid

import pymongo
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent

# ===================================================================
# CONFIGURATION
# ===================================================================

API_BASE_URL = "http://localhost:8000"
KONG_ADMIN_URL = "http://localhost:8001"
MONGO_HOST = "localhost"
MONGO_PORT = 27017
PROPAGATION_WAIT = 5  # seconds to wait for RabbitMQ event propagation


# ===================================================================
# FIXTURES
# ===================================================================

def wait_for_service(url, timeout=200):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(url).status_code == 200:
                return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"Service at {url} not ready")


@pytest.fixture(scope="module")
def db():
    client = pymongo.MongoClient(
        host=MONGO_HOST,
        port=MONGO_PORT,
        username=os.getenv("MONGO_USERNAME"),
        password=os.getenv("MONGO_PASSWORD"),
        authSource="admin",
    )
    yield client[os.getenv("DATABASE_NAME")]
    client.close()


# ===================================================================
# HELPERS
# ===================================================================

DEFAULT_ADDRESS = {
    "street": "123 Test Street",
    "city": "Testville",
    "state": "Test State",
    "postalCode": "12345",
    "country": "Test Country",
}


def unique_email():
    return f"test.{uuid.uuid4()}@mail.com"


def make_user_payload(email, address=None):
    """Return a fully-formed user creation payload."""
    return {
        "firstName": "Integration",
        "lastName": "Tester",
        "emails": [email],
        "deliveryAddress": address or DEFAULT_ADDRESS,
    }


def make_order_payload(user_id, email, address=None, items=None, status="under process"):
    """Return a fully-formed order creation payload."""
    return {
        "userId": user_id,
        "userEmails": [email],
        "deliveryAddress": address or DEFAULT_ADDRESS,
        "items": items or [{"itemId": "P002", "quantity": 1, "price": 10}],
        "orderStatus": status,
    }


def post_user(email, address=None):
    return requests.post(
        f"{API_BASE_URL}/users/",
        json=make_user_payload(email, address),
    )


def get_user(user_id):
    return requests.get(f"{API_BASE_URL}/users/{user_id}")


def put_user(user_id, payload):
    return requests.put(f"{API_BASE_URL}/users/{user_id}", json=payload)


def post_order(user_id, email, address=None, items=None, status="under process"):
    return requests.post(
        f"{API_BASE_URL}/orders/",
        json=make_order_payload(user_id, email, address, items, status),
    )


def get_orders():
    return requests.get(f"{API_BASE_URL}/orders")


def extract_id(body, *keys):
    """Return the first non-None value from *keys* found in *body*."""
    for key in keys:
        if body.get(key):
            return body[key]
    return None


def extract_email(doc):
    """Normalise email field — prefers userEmails (orders), then emails (users)."""
    return (doc.get("userEmails") or doc.get("emails") or [doc.get("email")])[0]


# ===================================================================
# TC 01 — Create & Retrieve User
# ===================================================================

class TestTC01_CreateAndRetrieveUser:
    def test_user_persisted_in_mongodb(self, db):
        """Created user must appear in the MongoDB users collection."""
        email = unique_email()
        create_resp = post_user(email=email)
        assert create_resp.status_code == 201

        user_id = extract_id(create_resp.json(), "userId", "id")
        mongo_doc = db["users"].find_one(
            {"$or": [{"userId": user_id}, {"id": user_id}]}
        )

        assert mongo_doc is not None, (
            f"User {user_id} not found in MongoDB users collection"
        )
        assert email in mongo_doc.get("emails", []), (
            f"Stored emails do not contain '{email}'. Doc: {mongo_doc}"
        )


# ===================================================================
# TC 02 — Create Order
# ===================================================================

class TestTC02_CreateOrder:
    def _create_user(self):
        """Create a user and return (user_id, email)."""
        email = unique_email()
        resp = post_user(email=email)
        assert resp.status_code == 201, resp.text
        user_id = extract_id(resp.json(), "userId", "id")
        return user_id, email

    def test_order_persisted_in_mongodb(self, db):
        """Created order must appear in the MongoDB orders collection with correct userId and email."""
        user_id, email = self._create_user()
        create_resp = post_order(user_id=user_id, email=email)
        assert create_resp.status_code == 201

        order_id = extract_id(create_resp.json(), "orderId", "id")
        mongo_doc = db["orders"].find_one(
            {"$or": [{"orderId": order_id}, {"id": order_id}]}
        )

        assert mongo_doc is not None, (
            f"Order {order_id} not found in MongoDB orders collection"
        )
        assert mongo_doc.get("userId") == user_id, (
            f"Stored userId '{mongo_doc.get('userId')}' != expected '{user_id}'"
        )
        assert email in mongo_doc.get("userEmails", []), (
            f"Stored userEmails do not contain '{email}'. Doc: {mongo_doc}"
        )


# ===================================================================
# TC 03 — Event-Driven Sync via RabbitMQ
# ===================================================================

class TestTC03_EventSync:
    def _setup_user_and_order(self):
        """Create a user and a linked order; return (user_id, order_id, email)."""
        email = unique_email()

        user_resp = post_user(email=email)
        assert user_resp.status_code == 201, user_resp.text
        user_id = extract_id(user_resp.json(), "userId", "id")

        order_resp = post_order(user_id=user_id, email=email)
        assert order_resp.status_code == 201, order_resp.text
        order_id = extract_id(order_resp.json(), "orderId", "id")

        return user_id, order_id, email

    def test_update_user_returns_200(self):
        """PUT /users/{id} with updated emails must return HTTP 200."""
        user_id, _, _ = self._setup_user_and_order()
        new_email = unique_email()

        resp = put_user(user_id, {"emails": [new_email]})

        assert resp.status_code == 200, (
            f"Expected 200 for user update, got {resp.status_code}: {resp.text}"
        )

    def test_updated_email_propagates_to_order_in_mongodb(self, db):
        """
        After a user email update, the linked order's userEmails must be updated
        in MongoDB within PROPAGATION_WAIT seconds (via RabbitMQ event).
        """
        user_id, order_id, _ = self._setup_user_and_order()
        new_email = unique_email()

        put_resp = put_user(user_id, {"emails": [new_email]})
        assert put_resp.status_code == 200

        # Poll until the event is processed or the deadline passes
        deadline = time.time() + PROPAGATION_WAIT
        order_doc = None
        while time.time() < deadline:
            order_doc = db["orders"].find_one(
                {"$or": [{"orderId": order_id}, {"id": order_id}]}
            )
            if order_doc and new_email in order_doc.get("userEmails", []):
                break
            time.sleep(0.5)

        assert order_doc is not None, f"Order {order_id} not found in MongoDB"
        assert new_email in order_doc.get("userEmails", []), (
            f"Order userEmails not updated after {PROPAGATION_WAIT}s. "
            f"Got {order_doc.get('userEmails')}, expected '{new_email}'"
        )


# ===================================================================
# STRANGLER-PATTERN HELPERS
# ===================================================================

def wait_for_kong(timeout=60):
    """Block until Kong Admin API is reachable or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{KONG_ADMIN_URL}/status", timeout=5).status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise TimeoutError("Kong did not become healthy in time")


def restart_kong(p_value):
    """
    Recreate the Kong container with the given P_VALUE env-var.
    P_VALUE controls the percentage of traffic routed to v1;
    (100 - P_VALUE) percent goes to v2.
    """
    env = os.environ.copy()
    env["P_VALUE"] = str(p_value)
    subprocess.run(
        [
            "docker", "compose",
            "-f", "docker-compose.test.yml",
            "up", "-d", "--force-recreate", "kong",
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    time.sleep(5)
    wait_for_kong()


def is_v2_response(body):
    """
    v2 adds a 'createdAt' timestamp to the user response; v1 does not.
    This field is used as the discriminator between the two versions.
    """
    return body.get("createdAt") is not None


def create_users_batch(n, prefix="batch"):
    """POST *n* users through the gateway using the correct payload shape."""
    results = []
    for i in range(n):
        email = f"{prefix}-{i}-{uuid.uuid4()}@mail.com"
        resp = requests.post(
            f"{API_BASE_URL}/users/",
            json=make_user_payload(email),
        )
        assert resp.status_code == 201, (
            f"Batch user creation failed: {resp.status_code} {resp.text}"
        )
        results.append(resp.json())
    return results


# ===================================================================
# TC 04 — API Gateway Routing (Strangler Pattern)
# Objective: Ensure Kong routes requests correctly between v1 and v2.
# ===================================================================

class TestTC04_StranglerPattern:
    """
    Uses Kong's P_VALUE env-var to control the v1/v2 traffic split:
      P=0   → 100 % to v2
      P=100 → 100 % to v1
      P=50  → roughly 50 % to each
    """

    @classmethod
    def teardown_class(cls):
        """Restore a neutral 50/50 split after all TC04 tests complete."""
        try:
            restart_kong(50)
        except Exception:
            pass

    # --- P = 0: all traffic must reach v2 ---

    def test_p0_all_traffic_reaches_v2(self):
        """With P=0, every user creation request must be served by v2."""
        restart_kong(0)
        results = create_users_batch(10, prefix="p0")

        v1_hits = [u for u in results if not is_v2_response(u)]
        assert len(v1_hits) == 0, (
            f"P=0: {len(v1_hits)}/10 requests unexpectedly reached v1"
        )

    # --- P = 100: all traffic must reach v1 ---

    def test_p100_all_traffic_reaches_v1(self):
        """With P=100, every user creation request must be served by v1."""
        restart_kong(100)
        results = create_users_batch(10, prefix="p100")

        v2_hits = [u for u in results if is_v2_response(u)]
        assert len(v2_hits) == 0, (
            f"P=100: {len(v2_hits)}/10 requests unexpectedly reached v2"
        )

    # --- P = 50: traffic must be split between both versions ---

    def test_p50_both_versions_receive_traffic(self):
        """With P=50, both v1 and v2 must receive at least one request."""
        restart_kong(50)
        results = create_users_batch(20, prefix="p50")

        v1_count = sum(1 for u in results if not is_v2_response(u))
        v2_count = len(results) - v1_count

        assert v1_count > 0, "P=50: no requests reached v1"
        assert v2_count > 0, "P=50: no requests reached v2"
