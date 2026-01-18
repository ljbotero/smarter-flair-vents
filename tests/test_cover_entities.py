import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from smarter_flair_vents.cover import FlairVentCover


class _FakeApi:
    def __init__(self):
        self.calls = []

    async def async_set_vent_position(self, vent_id, position):
        self.calls.append((vent_id, position))


class _FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.api = _FakeApi()
        self.refresh_called = False

    async def async_request_refresh(self):
        self.refresh_called = True

    def get_room_device_info_for_vent(self, vent_id):
        vent = self.data.get("vents", {}).get(vent_id, {})
        room = vent.get("room") or {}
        room_id = room.get("id")
        if not room_id:
            return None
        name = (room.get("attributes") or {}).get("name") or f"Room {room_id}"
        return {"identifiers": {("smarter_flair_vents", f"room_{room_id}")}, "name": name}


def test_cover_name_and_position():
    coordinator = _FakeCoordinator(
        {
            "vents": {
                "v1": {
                    "id": "v1",
                    "name": "Office",
                    "attributes": {"percent-open": 25},
                    "room": {"id": "room1", "attributes": {"name": "Office"}},
                }
            }
        }
    )
    entity = FlairVentCover(coordinator, "entry1", "v1")
    assert entity.name == "Office"
    assert entity.current_cover_position == 25
    assert entity.device_info["identifiers"] == {("smarter_flair_vents", "room_room1")}


def test_cover_set_position_calls_api():
    coordinator = _FakeCoordinator(
        {"vents": {"v1": {"id": "v1", "name": "Office", "attributes": {"percent-open": 25}}}}
    )
    entity = FlairVentCover(coordinator, "entry1", "v1")
    asyncio.run(entity.async_set_cover_position(position=75))
    assert coordinator.api.calls == [("v1", 75)]
    assert coordinator.refresh_called is True
    assert entity.current_cover_position == 75


def test_cover_open_close():
    coordinator = _FakeCoordinator(
        {"vents": {"v1": {"id": "v1", "name": "Office", "attributes": {"percent-open": 25}}}}
    )
    entity = FlairVentCover(coordinator, "entry1", "v1")
    asyncio.run(entity.async_open_cover())
    asyncio.run(entity.async_close_cover())
    assert ("v1", 100) in coordinator.api.calls
    assert ("v1", 0) in coordinator.api.calls


def test_cover_pending_position_keeps_state_until_refresh():
    coordinator = _FakeCoordinator(
        {"vents": {"v1": {"id": "v1", "name": "Office", "attributes": {"percent-open": 20}}}}
    )
    entity = FlairVentCover(coordinator, "entry1", "v1")
    asyncio.run(entity.async_set_cover_position(position=57))
    assert entity.current_cover_position == 57

    entity._handle_coordinator_update()
    assert entity.current_cover_position == 57

    entity._pending_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    entity._handle_coordinator_update()
    assert entity.current_cover_position == 20

def test_cover_async_setup_entry_adds_entities():
    from smarter_flair_vents import cover as cover_module

    coordinator = _FakeCoordinator(
        {"vents": {"v1": {"id": "v1", "name": "Office", "attributes": {}}}}
    )
    hass = SimpleNamespace(data={"smarter_flair_vents": {"entry1": coordinator}})
    entry = SimpleNamespace(entry_id="entry1")
    added = []

    def add_entities(entities):
        added.extend(entities)

    asyncio.run(cover_module.async_setup_entry(hass, entry, add_entities))
    assert len(added) == 1
