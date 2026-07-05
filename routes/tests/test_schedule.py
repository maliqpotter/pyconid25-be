import uuid
from datetime import datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import alembic.config
from fastapi.testclient import TestClient

from core.security import generate_token_from_user
from main import app
from models import db, engine, get_db_sync, get_db_sync_for_test
from models.Room import Room
from models.Schedule import Schedule
from models.ScheduleType import ScheduleType
from models.Speaker import Speaker
from models.SpeakerSchedule import SpeakerSchedule
from models.SpeakerType import SpeakerType
from models.Stream import Stream, StreamStatus
from models.User import MANAGEMENT_PARTICIPANT, User
from schemas.user_profile import ParticipantType


def _attach_speaker(db_session, schedule, speaker, order=1, type_="Main Speaker"):
    """Helper: attach a speaker to a schedule via the speaker_schedule junction."""
    junction = SpeakerSchedule(
        speaker_id=speaker.id,
        schedule_id=schedule.id,
        type=type_,
        order=order,
    )
    db_session.add(junction)


class TestSchedule(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        alembic_args = ["upgrade", "head"]
        alembic.config.main(argv=alembic_args)
        # connect to the database
        self.connection = engine.connect()

        # begin a non-ORM transaction
        self.trans = self.connection.begin()

        # bind an individual Session to the connection, selecting
        # "create_savepoint" join_transaction_mode
        self.db = db(bind=self.connection, join_transaction_mode="create_savepoint")

        # Create test data
        self.user_management = User(
            id="123e4567-e89b-12d3-a456-426614174000",
            username="admin",
            participant_type=MANAGEMENT_PARTICIPANT,
        )
        self.db.add(self.user_management)

        self.user_non_management = User(
            username="regular_user",
            participant_type=ParticipantType.NON_PARTICIPANT,
        )
        self.db.add(self.user_non_management)

        self.speaker_type = SpeakerType(name="Keynote Speaker")
        self.db.add(self.speaker_type)

        self.room = Room(name="Main Hall")
        self.db.add(self.room)

        self.schedule_type = ScheduleType(name="Talk")
        self.db.add(self.schedule_type)

        self.user_speaker = User(
            username="speaker_user",
            first_name="Jane",
            last_name="Doe",
            bio="Expert speaker",
            email="jane@example.com",
            share_my_email_and_phone_number=True,
            share_my_job_and_company=False,
            share_my_public_social_media=False,
        )
        self.db.add(self.user_speaker)

        self.speaker = Speaker(
            user=self.user_speaker,
            speaker_type=self.speaker_type,
        )
        self.db.add(self.speaker)

        self.user_speaker_2 = User(
            username="speaker_user_2",
            first_name="John",
            last_name="Doe",
            bio="Second expert speaker",
            email="john@example.com",
            share_my_email_and_phone_number=True,
            share_my_job_and_company=False,
            share_my_public_social_media=False,
        )
        self.db.add(self.user_speaker_2)
        self.speaker_2 = Speaker(
            user=self.user_speaker_2,
            speaker_type=self.speaker_type,
        )
        self.db.add(self.speaker_2)

        self.db.commit()

    @patch("core.mux_service.mux_service.create_live_stream")
    async def test_create_schedule_success(self, mock_create_stream):
        # Given
        mock_create_stream.return_value = (
            "mux_stream_123",
            "stream_key_123",
            "playback_id_123",
        )

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        payload = {
            "title": "Python Best Practices",
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                }
            ],
            "room_id": str(self.room.id),
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Learn Python best practices",
            "presentation_language": "English",
            "slide_language": "English",
            "slide_link": "https://slides.example.com",
            "tags": ["python", "best-practices"],
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }

        # When
        response = client.post(
            "/schedule/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Python Best Practices")
        self.assertEqual(len(data["speakers"]), 1)
        self.assertEqual(data["speakers"][0]["speaker"]["id"], str(self.speaker.id))
        self.assertEqual(data["speakers"][0]["order"], 1)
        self.assertEqual(data["speakers"][0]["type"], "Main Speaker")
        mock_create_stream.assert_called_once_with(is_public=True)

    @patch("core.mux_service.mux_service.create_live_stream")
    async def test_create_schedule_without_speaker_success(self, mock_create_stream):
        # Given
        mock_create_stream.return_value = (
            "mux_stream_123",
            "stream_key_123",
            "playback_id_123",
        )

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        payload = {
            "title": "Schedule Without Speaker",
            "room_id": str(self.room.id),
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Schedule without speaker",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python"],
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }

        # When
        response = client.post(
            "/schedule/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Schedule Without Speaker")
        self.assertEqual(data["speakers"], [])
        mock_create_stream.assert_called_once_with(is_public=True)

    @patch("core.mux_service.mux_service.create_live_stream")
    async def test_create_schedule_multi_speaker_allowed(self, mock_create_stream):
        # """After the relationship became many-to-many, one speaker may appear in multiple
        # schedules (e.g. as a co-speaker in a panel). Creating a second schedule with the
        # same speaker MUST be allowed (replacing the old test that expected a 422)
        # "speaker_already_scheduled").
        # Given
        mock_create_stream.return_value = (
            "mux_stream_123",
            "stream_key_123",
            "playback_id_123",
        )

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)
        existing_schedule = Schedule(
            title="Existing Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Existing schedule for speaker",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(existing_schedule)
        self.db.flush()
        _attach_speaker(self.db, existing_schedule, self.speaker)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        new_start = datetime.now() + timedelta(hours=3)
        new_end = new_start + timedelta(hours=1)
        payload = {
            "title": "Second Schedule Same Speaker",
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                }
            ],
            "room_id": str(self.room.id),
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Should succeed: multi-speaker feature allows this",
            "presentation_language": "English",
            "slide_language": "English",
            "slide_link": "https://slides.example.com",
            "tags": ["python"],
            "start": new_start.isoformat(),
            "end": new_end.isoformat(),
        }

        # When
        response = client.post(
            "/schedule/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 201)
        mock_create_stream.assert_called_once_with(is_public=True)

    async def test_create_schedule_unauthorized(self):
        # Given
        token, _ = await generate_token_from_user(
            db=self.db, user=self.user_non_management
        )
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        payload = {
            "title": "Test Schedule",
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                }
            ],
            "room_id": str(self.room.id),
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Test",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": [],
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }

        # When
        response = client.post(
            "/schedule/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 403)

    async def test_update_schedule_success(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Original Title",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Original description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        payload = {
            "title": "Updated Title",
            "room_id": str(self.room.id),
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                }
            ],
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Updated description",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python", "update"],
            "start": str(start_time),
            "end": str(end_time),
        }

        # When
        response = client.put(
            f"/schedule/{schedule.id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Updated Title")
        self.assertEqual(data["description"], "Updated description")

    async def test_update_schedule_reorder_speakers(self):
        # Given — schedule with two speakers in order [Dima, Bima]
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Two Speakers",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Has two speakers",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker, order=1)
        _attach_speaker(self.db, schedule, self.speaker_2, order=2)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        payload = {
            "title": "Two Speakers",
            "room_id": str(self.room.id),
            "speakers": [
                {
                    "speaker_id": str(self.speaker_2.id),
                    "order": 1,
                    "type": "Main Speaker",
                },
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 2,
                    "type": "Co Speaker",
                },
            ],
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Reordered speakers",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python"],
            "start": str(start_time),
            "end": str(end_time),
        }

        # When — reorder to [Bima, Dima]
        response = client.put(
            f"/schedule/{schedule.id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["speakers"]), 2)
        self.assertEqual(data["speakers"][0]["speaker"]["id"], str(self.speaker_2.id))
        self.assertEqual(data["speakers"][0]["order"], 1)
        self.assertEqual(data["speakers"][1]["speaker"]["id"], str(self.speaker.id))
        self.assertEqual(data["speakers"][1]["order"], 2)

    async def test_update_schedule_replace_speaker(self):
        # Given — schedule with [Dima, Bima], replace Bima with a new speaker
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        user_speaker_3 = User(
            username="speaker_user_3",
            first_name="Budi",
            last_name="Santoso",
            bio="Third speaker",
            email="budi@example.com",
            share_my_email_and_phone_number=True,
            share_my_job_and_company=False,
            share_my_public_social_media=False,
        )
        self.db.add(user_speaker_3)
        speaker_3 = Speaker(user=user_speaker_3, speaker_type=self.speaker_type)
        self.db.add(speaker_3)

        schedule = Schedule(
            title="Replace Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Has two speakers",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker, order=1)
        _attach_speaker(self.db, schedule, self.speaker_2, order=2)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        payload = {
            "title": "Replace Speaker",
            "room_id": str(self.room.id),
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                },
                {
                    "speaker_id": str(speaker_3.id),
                    "order": 2,
                    "type": "Co Speaker",
                },
            ],
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Replaced speaker",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python"],
            "start": str(start_time),
            "end": str(end_time),
        }

        # When — replace Bima with Budi
        response = client.put(
            f"/schedule/{schedule.id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["speakers"]), 2)
        speaker_ids = [s["speaker"]["id"] for s in data["speakers"]]
        self.assertIn(str(self.speaker.id), speaker_ids)
        self.assertIn(str(speaker_3.id), speaker_ids)
        self.assertNotIn(str(self.speaker_2.id), speaker_ids)

    async def test_update_schedule_clear_speakers(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Schedule With Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Has speaker initially",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        payload = {
            "title": "Schedule Without Speaker",
            "room_id": str(self.room.id),
            "speakers": [],
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Speaker cleared",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python"],
            "start": str(start_time),
            "end": str(end_time),
        }

        # When
        response = client.put(
            f"/schedule/{schedule.id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Schedule Without Speaker")
        self.assertEqual(data["speakers"], [])

    async def test_update_schedule_speaker_can_be_shared_across_schedules(self):
        # After many-to-many, assigning a speaker already used in another
        # schedule MUST succeed (replacing the old test)
        # "speaker_already_scheduled_in_other_schedule").
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule_to_update = Schedule(
            title="Schedule To Update",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Schedule that will be updated",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule_to_update)

        other_schedule = Schedule(
            title="Other Schedule With Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Other schedule using this speaker",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time + timedelta(hours=2),
            end=end_time + timedelta(hours=2),
        )
        self.db.add(other_schedule)
        self.db.flush()
        _attach_speaker(self.db, other_schedule, self.speaker)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        payload = {
            "title": "Schedule To Update",
            "room_id": str(self.room.id),
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Co Speaker",
                }
            ],
            "schedule_type_id": str(self.schedule_type.id),
            "description": "Assign shared speaker",
            "presentation_language": "English",
            "slide_language": "English",
            "tags": ["python"],
            "start": str(start_time),
            "end": str(end_time),
        }

        # When
        response = client.put(
            f"/schedule/{schedule_to_update.id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)

    async def test_update_schedule_not_found(self):
        # Given
        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        non_existent_id = str(uuid.uuid4())
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)
        payload = {
            "title": "Updated Title",
            "room_id": str(self.room.id),
            "speakers": [
                {
                    "speaker_id": str(self.speaker.id),
                    "order": 1,
                    "type": "Main Speaker",
                }
            ],
            "schedule_type_id": str(self.schedule_type.id),
            "start": str(start_time),
            "end": str(end_time),
        }

        # When
        response = client.put(
            f"/schedule/{non_existent_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        print(response.json())

        # Expect
        self.assertEqual(response.status_code, 404)

    @patch("core.mux_service.mux_service.delete_live_stream")
    async def test_delete_schedule_success(self, mock_delete_stream):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Schedule to Delete",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_123",
            mux_playback_id="playback_123",
            mux_stream_key="stream_key_123",
            status=StreamStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.delete(
            f"/schedule/{schedule.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 204)
        mock_delete_stream.assert_called_once_with("mux_stream_123")

    async def test_get_schedule_by_id_success(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Test Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(f"/schedule/{schedule.id}")

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Test Schedule")
        self.assertEqual(
            data["speakers"][0]["speaker"]["user"]["email"], "jane@example.com"
        )
        self.assertIsNone(data["speakers"][0]["speaker"]["user"]["company"])

    async def test_get_schedule_by_id_without_speaker(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Schedule Without Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="No speaker",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(f"/schedule/{schedule.id}")

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Schedule Without Speaker")
        self.assertEqual(data["speakers"], [])

    async def test_get_schedule_by_id_not_found(self):
        # Given
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)
        non_existent_id = str(uuid.uuid4())

        # When
        response = client.get(f"/schedule/{non_existent_id}")

        # Expect
        self.assertEqual(response.status_code, 404)

    async def test_get_schedule_cms(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="CMS Test Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_123",
            mux_playback_id="playback_123",
            mux_stream_key="stream_key_123",
            status=StreamStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            "/schedule/cms",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        self.assertEqual(data["results"][0]["title"], "CMS Test Schedule")
        self.assertEqual(data["results"][0]["stream_key"], "stream_key_123")

    async def test_get_schedule_cms_forbidden(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="CMS Test Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_123",
            mux_playback_id="playback_123",
            mux_stream_key="stream_key_123",
            status=StreamStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(
            db=self.db, user=self.user_non_management
        )
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            "/schedule/cms",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 403)

    async def test_get_schedule_cms_without_speaker(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="CMS Schedule Without Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="CMS no speaker",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_456",
            mux_playback_id="playback_456",
            mux_stream_key="stream_key_456",
            status=StreamStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            "/schedule/cms",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        result = next(
            r for r in data["results"] if r["title"] == "CMS Schedule Without Speaker"
        )
        self.assertEqual(result["speakers"], [])
        self.assertEqual(result["stream_key"], "stream_key_456")

    async def test_get_mux_stream_by_schedule_id_success(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Stream Test Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_123",
            mux_playback_id="playback_123",
            mux_stream_key="stream_key_123",
            status=StreamStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            f"/schedule/{schedule.id}/stream",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["stream_id"], str(stream.id))
        self.assertEqual(data["stream_key"], "stream_key_123")
        self.assertEqual(data["playback_id"], "playback_123")

    async def test_get_mux_stream_by_schedule_id_unauthorized(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Stream Test Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.commit()

        token, _ = await generate_token_from_user(
            db=self.db, user=self.user_non_management
        )
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            f"/schedule/{schedule.id}/stream",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 403)

    @patch("core.mux_service.mux_service.create_live_stream")
    @patch("core.mux_service.mux_service.delete_live_stream")
    async def test_recreate_stream_success(
        self, mock_delete_stream, mock_create_stream
    ):
        # Given
        mock_create_stream.return_value = (
            "new_mux_stream_123",
            "new_stream_key_123",
            "new_playback_id_123",
        )

        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Recreate Stream Test",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="old_mux_stream_123",
            mux_playback_id="old_playback_123",
            mux_stream_key="old_stream_key_123",
            status=StreamStatus.ENDED,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.post(
            f"/schedule/{schedule.id}/recreate-stream",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 204)
        mock_delete_stream.assert_called_once_with("old_mux_stream_123")
        mock_create_stream.assert_called_once_with(is_public=True)

    @patch("core.mux_service.mux_service.create_live_stream")
    @patch("core.mux_service.mux_service.delete_live_stream")
    async def test_recreate_stream_when_streaming(
        self, mock_delete_stream, mock_create_stream
    ):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Streaming Schedule",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.flush()
        _attach_speaker(self.db, schedule, self.speaker)
        self.db.commit()

        stream = Stream(
            schedule_id=schedule.id,
            is_public=True,
            mux_live_stream_id="mux_stream_123",
            mux_playback_id="playback_123",
            mux_stream_key="stream_key_123",
            status=StreamStatus.STREAMING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.db.add(stream)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.post(
            f"/schedule/{schedule.id}/recreate-stream",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect
        self.assertEqual(response.status_code, 400)
        mock_delete_stream.assert_not_called()
        mock_create_stream.assert_not_called()

    async def test_get_schedule_list(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule1 = Schedule(
            title="Schedule 1",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description 1",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule1)
        self.db.flush()
        _attach_speaker(self.db, schedule1, self.speaker)

        schedule2 = Schedule(
            title="Schedule 2",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Test description 2",
            presentation_language="English",
            slide_language="English",
            tags=["django"],
            start=start_time + timedelta(hours=2),
            end=end_time + timedelta(hours=2),
        )
        self.db.add(schedule2)
        self.db.flush()
        _attach_speaker(self.db, schedule2, self.speaker)
        self.db.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get("/schedule/", params={"page_size": 10, "page": 1})

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)
        self.assertGreaterEqual(len(data["results"]), 2)

    async def test_get_schedule_list_with_and_without_speaker(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule_with_speaker = Schedule(
            title="Schedule With Speaker",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Has speaker",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule_with_speaker)
        self.db.flush()
        _attach_speaker(self.db, schedule_with_speaker, self.speaker)

        schedule_without_speaker = Schedule(
            title="Schedule Without Speaker In List",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="No speaker in list",
            presentation_language="English",
            slide_language="English",
            tags=["django"],
            start=start_time + timedelta(hours=2),
            end=end_time + timedelta(hours=2),
        )
        self.db.add(schedule_without_speaker)
        self.db.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get("/schedule/", params={"page_size": 10, "page": 1})

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = [item["title"] for item in data["results"]]
        self.assertIn("Schedule With Speaker", titles)
        self.assertIn("Schedule Without Speaker In List", titles)

        schedule_without_speaker_data = next(
            item
            for item in data["results"]
            if item["title"] == "Schedule Without Speaker In List"
        )
        self.assertEqual(schedule_without_speaker_data["speakers"], [])

    async def test_get_schedule_list_with_search(self):
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule1 = Schedule(
            title="Python Advanced",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Advanced Python topics",
            presentation_language="English",
            slide_language="English",
            tags=["python"],
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule1)
        self.db.flush()
        _attach_speaker(self.db, schedule1, self.speaker)

        schedule2 = Schedule(
            title="Django Basics",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            description="Basic Django",
            presentation_language="English",
            slide_language="English",
            tags=["django"],
            start=start_time + timedelta(hours=2),
            end=end_time + timedelta(hours=2),
        )
        self.db.add(schedule2)
        self.db.flush()
        _attach_speaker(self.db, schedule2, self.speaker)
        self.db.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When
        response = client.get(
            "/schedule", params={"page_size": 10, "page": 1, "search": "Python"}
        )

        # Expect
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(data["count"], 0)

    async def test_create_schedule_duplicate_order_rejected(self):
        """Create a schedule with duplicate speaker orders should return 422."""
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When - same order=1 for both speakers
        response = client.post(
            "/schedule/",
            json={
                "title": "Duplicate Order Test",
                "room_id": str(self.room.id),
                "schedule_type_id": str(self.schedule_type.id),
                "speakers": [
                    {
                        "speaker_id": str(self.speaker.id),
                        "order": 1,
                        "type": "Main Speaker",
                    },
                    {
                        "speaker_id": str(self.speaker_2.id),
                        "order": 1,
                        "type": "Co Speaker",
                    },
                ],
                "description": "Test duplicate order",
                "presentation_language": "English",
                "slide_language": "English",
                "tags": ["test"],
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect - 422 Unprocessable Entity
        self.assertEqual(response.status_code, 422)
        self.assertIn("duplicate order", response.text.lower())

    async def test_create_schedule_invalid_type_rejected(self):
        """Create a schedule with an invalid speaker type should return 422."""
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When - invalid type
        response = client.post(
            "/schedule/",
            json={
                "title": "Invalid Type Test",
                "room_id": str(self.room.id),
                "schedule_type_id": str(self.schedule_type.id),
                "speakers": [
                    {
                        "speaker_id": str(self.speaker.id),
                        "order": 1,
                        "type": "InvalidRole",
                    },
                ],
                "description": "Test invalid type",
                "presentation_language": "English",
                "slide_language": "English",
                "tags": ["test"],
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect - 422 Unprocessable Entity
        self.assertEqual(response.status_code, 422)
        self.assertIn("type", response.text.lower())

    async def test_create_schedule_speaker_not_found_rejected(self):
        """Create a schedule with a non-existent speaker ID should return 400."""
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        fake_speaker_id = str(uuid.uuid4())

        # When - speaker_id that doesn't exist
        response = client.post(
            "/schedule/",
            json={
                "title": "Speaker Not Found Test",
                "room_id": str(self.room.id),
                "schedule_type_id": str(self.schedule_type.id),
                "speakers": [
                    {"speaker_id": fake_speaker_id, "order": 1, "type": "Main Speaker"},
                ],
                "description": "Test speaker not found",
                "presentation_language": "English",
                "slide_language": "English",
                "tags": ["test"],
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect - 400 Bad Request
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("not found", data["message"])

    async def test_create_schedule_order_zero_rejected(self):
        """Create a schedule with order=0 should return 422."""
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When - order = 0
        response = client.post(
            "/schedule/",
            json={
                "title": "Order Zero Test",
                "room_id": str(self.room.id),
                "schedule_type_id": str(self.schedule_type.id),
                "speakers": [
                    {
                        "speaker_id": str(self.speaker.id),
                        "order": 0,
                        "type": "Main Speaker",
                    },
                ],
                "description": "Test order zero",
                "presentation_language": "English",
                "slide_language": "English",
                "tags": ["test"],
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect - 422 Unprocessable Entity
        self.assertEqual(response.status_code, 422)
        self.assertIn("greater_than_equal", response.text)

    async def test_update_schedule_duplicate_order_rejected(self):
        """Update a schedule with duplicate speaker orders should return 422."""
        # Given
        start_time = datetime.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        schedule = Schedule(
            title="Update Duplicate Order",
            room_id=self.room.id,
            schedule_type_id=self.schedule_type.id,
            start=start_time,
            end=end_time,
        )
        self.db.add(schedule)
        self.db.commit()

        token, _ = await generate_token_from_user(db=self.db, user=self.user_management)
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When - update with duplicate order
        response = client.put(
            f"/schedule/{schedule.id}",
            json={
                "title": "Update Duplicate Order",
                "room_id": str(self.room.id),
                "schedule_type_id": str(self.schedule_type.id),
                "speakers": [
                    {
                        "speaker_id": str(self.speaker.id),
                        "order": 1,
                        "type": "Main Speaker",
                    },
                    {
                        "speaker_id": str(self.speaker_2.id),
                        "order": 1,
                        "type": "Co Speaker",
                    },
                ],
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Expect - 422
        self.assertEqual(response.status_code, 422)
        self.assertIn("duplicate order", response.text.lower())

    def tearDown(self) -> None:
        self.db.close()

        # rollback - everything that happened with the
        # Session above (including calls to commit())
        # is rolled back.
        self.trans.rollback()

        # return connection to the Engine
        self.connection.close()
