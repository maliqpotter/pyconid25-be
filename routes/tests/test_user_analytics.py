import uuid
from datetime import datetime
from unittest import IsolatedAsyncioTestCase

import alembic.config
from fastapi.testclient import TestClient
from pytz import timezone

from core.security import generate_hash_password, generate_token_from_user
from main import app
from models import db, engine, get_db_sync, get_db_sync_for_test
from models.City import City
from models.Country import Country
from models.Payment import PaymentStatus
from models.State import State
from models.Ticket import Ticket
from models.User import MANAGEMENT_PARTICIPANT, User
from repository import payment as paymentRepo
from settings import TZ


class TestUserAnalytics(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        alembic_args = ["upgrade", "head"]
        alembic.config.main(argv=alembic_args)

        self.connection = engine.connect()
        self.trans = self.connection.begin()
        self.db = db(bind=self.connection, join_transaction_mode="create_savepoint")

        self._setup_locations()
        self._setup_users_and_payments()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.db.close()
        self.trans.rollback()
        self.connection.close()

    def _setup_locations(self):
        self.db.query(City).delete()
        self.db.query(State).delete()
        self.db.query(Country).delete()
        self.db.commit()

        countries = [
            Country(id=102, name="Indonesia", iso2="ID", iso3="IDN"),
            Country(id=231, name="United States", iso2="US", iso3="USA"),
        ]
        for country in countries:
            self.db.merge(country)

        states = [
            State(id=1836, name="Jakarta", country_id=102, country_code="ID"),
            State(id=1837, name="West Java", country_id=102, country_code="ID"),
            State(id=1416, name="California", country_id=231, country_code="US"),
        ]
        for state in states:
            self.db.merge(state)

        cities = [
            City(id=38932, name="Jakarta Pusat", state_id=1836, country_id=102),
            City(id=38934, name="Bandung", state_id=1837, country_id=102),
            City(id=10001, name="Los Angeles", state_id=1416, country_id=231),
        ]
        for city in cities:
            self.db.merge(city)

        self.db.commit()

    def _setup_users_and_payments(self):
        now = datetime.now(timezone(TZ))

        self.admin_user = User(
            username="analytics-admin",
            email="analytics-admin@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            participant_type=MANAGEMENT_PARTICIPANT,
            created_at=now,
            updated_at=now,
        )
        self.regular_user = User(
            username="analytics-regular",
            email="analytics-regular@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            participant_type="In Person",
            country_id=102,
            state_id=1836,
            city_id=38932,
            created_at=now,
            updated_at=now,
        )
        self.db.add(self.admin_user)
        self.db.add(self.regular_user)

        ticket = Ticket(
            id=uuid.uuid4(),
            name="Analytics Ticket",
            price=100000,
            user_participant_type="In Person",
            is_sold_out=False,
            is_active=True,
            description="Ticket for analytics tests",
        )
        self.db.add(ticket)
        self.db.commit()
        self.ticket = ticket

        # Bandung x2 paid
        for i in range(2):
            user = User(
                username=f"bandung-user-{i}",
                email=f"bandung{i}@example.com",
                password=generate_hash_password("password"),
                is_active=True,
                country_id=102,
                state_id=1837,
                city_id=38934,
                created_at=now,
                updated_at=now,
            )
            self.db.add(user)
            self.db.flush()
            paymentRepo.create_payment(
                db=self.db,
                user_id=user.id,
                amount=100000,
                ticket_id=str(ticket.id),
                status=PaymentStatus.PAID,
            )

        # Jakarta Pusat x1 paid
        jakarta_user = User(
            username="jakarta-user",
            email="jakarta@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            country_id=102,
            state_id=1836,
            city_id=38932,
            created_at=now,
            updated_at=now,
        )
        self.db.add(jakarta_user)
        self.db.flush()
        paymentRepo.create_payment(
            db=self.db,
            user_id=jakarta_user.id,
            amount=100000,
            ticket_id=str(ticket.id),
            status=PaymentStatus.PAID,
        )

        # Los Angeles x1 paid
        la_user = User(
            username="la-user",
            email="la@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            country_id=231,
            state_id=1416,
            city_id=10001,
            created_at=now,
            updated_at=now,
        )
        self.db.add(la_user)
        self.db.flush()
        paymentRepo.create_payment(
            db=self.db,
            user_id=la_user.id,
            amount=100000,
            ticket_id=str(ticket.id),
            status=PaymentStatus.PAID,
        )

        # Unpaid user in Bandung — should not be counted
        unpaid_user = User(
            username="unpaid-bandung",
            email="unpaid@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            country_id=102,
            state_id=1837,
            city_id=38934,
            created_at=now,
            updated_at=now,
        )
        self.db.add(unpaid_user)
        self.db.flush()
        paymentRepo.create_payment(
            db=self.db,
            user_id=unpaid_user.id,
            amount=100000,
            ticket_id=str(ticket.id),
            status=PaymentStatus.UNPAID,
        )

        # Deleted paid user — should not be counted
        deleted_user = User(
            username="deleted-user",
            email="deleted@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            country_id=102,
            state_id=1837,
            city_id=38934,
            created_at=now,
            updated_at=now,
            deleted_at=now,
        )
        self.db.add(deleted_user)
        self.db.flush()
        paymentRepo.create_payment(
            db=self.db,
            user_id=deleted_user.id,
            amount=100000,
            ticket_id=str(ticket.id),
            status=PaymentStatus.PAID,
        )

        # Paid user without location — should not appear in location groups
        no_location_user = User(
            username="no-location",
            email="nolocation@example.com",
            password=generate_hash_password("password"),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(no_location_user)
        self.db.flush()
        paymentRepo.create_payment(
            db=self.db,
            user_id=no_location_user.id,
            amount=100000,
            ticket_id=str(ticket.id),
            status=PaymentStatus.PAID,
        )

        self.db.commit()

    async def _management_headers(self):
        token, _ = await generate_token_from_user(db=self.db, user=self.admin_user)
        return {"Authorization": f"Bearer {token}"}

    async def _regular_headers(self):
        token, _ = await generate_token_from_user(db=self.db, user=self.regular_user)
        return {"Authorization": f"Bearer {token}"}

    async def test_get_by_city_unauthorized(self):
        response = self.client.get("/analitic/user/city/")
        self.assertEqual(response.status_code, 401)

    async def test_get_by_city_forbidden(self):
        headers = await self._regular_headers()
        response = self.client.get("/analitic/user/city/", headers=headers)
        self.assertEqual(response.status_code, 403)

    async def test_get_by_city_success(self):
        headers = await self._management_headers()
        response = self.client.get("/analitic/user/city/", headers=headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)

        by_name = {item["city"]["name"]: item for item in data}
        self.assertEqual(by_name["Bandung"]["count"], 2)
        self.assertEqual(by_name["Bandung"]["city"]["id"], 38934)
        self.assertEqual(by_name["Jakarta Pusat"]["count"], 1)
        self.assertEqual(by_name["Los Angeles"]["count"], 1)
        self.assertEqual(data[0]["city"]["name"], "Bandung")

    async def test_get_by_state_success(self):
        headers = await self._management_headers()
        response = self.client.get("/analitic/user/state/", headers=headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)

        by_name = {item["state"]["name"]: item for item in data}
        self.assertEqual(by_name["West Java"]["count"], 2)
        self.assertEqual(by_name["West Java"]["state"]["id"], 1837)
        self.assertEqual(by_name["Jakarta"]["count"], 1)
        self.assertEqual(by_name["California"]["count"], 1)
        self.assertEqual(data[0]["state"]["name"], "West Java")

    async def test_get_by_country_success(self):
        headers = await self._management_headers()
        response = self.client.get("/analitic/user/country/", headers=headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        by_name = {item["country"]["name"]: item for item in data}
        self.assertEqual(by_name["Indonesia"]["count"], 3)
        self.assertEqual(by_name["Indonesia"]["country"]["id"], 102)
        self.assertEqual(by_name["United States"]["count"], 1)
        self.assertEqual(data[0]["country"]["name"], "Indonesia")

    async def test_get_by_state_unauthorized(self):
        response = self.client.get("/analitic/user/state/")
        self.assertEqual(response.status_code, 401)

    async def test_get_by_country_unauthorized(self):
        response = self.client.get("/analitic/user/country/")
        self.assertEqual(response.status_code, 401)
