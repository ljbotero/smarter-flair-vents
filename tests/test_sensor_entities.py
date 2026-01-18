from types import SimpleNamespace

from smarter_flair_vents.sensor import (
    FlairPuckSensor,
    FlairSystemSensor,
    FlairVentSensor,
    PUCK_SENSOR_DESCRIPTIONS,
    VENT_SENSOR_DESCRIPTIONS,
)


class _FakeCoordinator:
    def __init__(self, data):
        self.data = data

    def get_vent_efficiency_percent(self, vent_id, mode):
        return 42.0

    def get_room_device_info_for_puck(self, puck_id):
        puck = self.data.get("pucks", {}).get(puck_id, {})
        room = puck.get("room") or {}
        room_id = room.get("id")
        if not room_id:
            return None
        name = (room.get("attributes") or {}).get("name") or f"Room {room_id}"
        return {"identifiers": {("smarter_flair_vents", f"room_{room_id}")}, "name": name}

    def get_room_device_info_for_vent(self, vent_id):
        vent = self.data.get("vents", {}).get(vent_id, {})
        room = vent.get("room") or {}
        room_id = room.get("id")
        if not room_id:
            return None
        name = (room.get("attributes") or {}).get("name") or f"Room {room_id}"
        return {"identifiers": {("smarter_flair_vents", f"room_{room_id}")}, "name": name}

    def get_vent_last_reading(self, vent_id):
        return None

    def get_strategy_metrics(self):
        return {"last_strategy": "hybrid", "strategies": {}}


def test_puck_sensor_values_and_battery():
    coordinator = _FakeCoordinator(
        {
            "pucks": {
                "p1": {
                    "id": "p1",
                    "name": "Bedroom Puck",
                    "attributes": {
                        "current-temperature-c": 21.5,
                        "current-humidity": 40,
                        "system-voltage": 2.8,
                        "room-pressure": 101.0,
                        "rssi": -40,
                    },
                    "room": {"id": "room1", "attributes": {"name": "Bedroom"}},
                }
            }
        }
    )

    temp_desc = PUCK_SENSOR_DESCRIPTIONS[0]
    temp_sensor = FlairPuckSensor(coordinator, "entry", "p1", temp_desc)
    assert temp_sensor.native_value == 21.5
    assert temp_sensor.device_info["identifiers"] == {("smarter_flair_vents", "room_room1")}

    humidity_desc = PUCK_SENSOR_DESCRIPTIONS[1]
    humidity_sensor = FlairPuckSensor(coordinator, "entry", "p1", humidity_desc)
    assert humidity_sensor.native_value == 40

    battery_desc = next(desc for desc in PUCK_SENSOR_DESCRIPTIONS if desc.key == "battery")
    battery_sensor = FlairPuckSensor(coordinator, "entry", "p1", battery_desc)
    assert battery_sensor.native_value == 50

    pressure_desc = next(desc for desc in PUCK_SENSOR_DESCRIPTIONS if desc.key == "pressure")
    pressure_sensor = FlairPuckSensor(coordinator, "entry", "p1", pressure_desc)
    assert pressure_sensor.native_value == 101.0


def test_vent_sensor_values():
    coordinator = _FakeCoordinator(
        {
            "vents": {
                "v1": {
                    "id": "v1",
                    "name": "Office Vent",
                    "attributes": {
                        "percent-open": 45,
                        "duct-temperature-c": 19.2,
                        "system-voltage": 2.9,
                        "rssi": -50,
                    },
                    "room": {"id": "room2", "attributes": {"name": "Office"}},
                }
            }
        }
    )

    for desc in VENT_SENSOR_DESCRIPTIONS:
        sensor = FlairVentSensor(coordinator, "entry", "v1", desc)
        if desc.key != "last_reading":
            assert sensor.native_value is not None
        assert sensor.device_info["identifiers"] == {("smarter_flair_vents", "room_room2")}


def test_async_setup_entry_adds_entities():
    from smarter_flair_vents import sensor as sensor_module

    coordinator = _FakeCoordinator(
        {
            "pucks": {"p1": {"id": "p1", "attributes": {}}},
            "vents": {"v1": {"id": "v1", "attributes": {}}},
        }
    )
    hass = SimpleNamespace(data={"smarter_flair_vents": {"entry1": coordinator}})
    entry = SimpleNamespace(entry_id="entry1")
    added = []

    def add_entities(entities):
        added.extend(entities)

    import asyncio

    asyncio.run(sensor_module.async_setup_entry(hass, entry, add_entities))
    assert len(added) == len(PUCK_SENSOR_DESCRIPTIONS) + len(VENT_SENSOR_DESCRIPTIONS) + 1


def test_system_sensor_exposes_metrics():
    coordinator = _FakeCoordinator({"pucks": {}, "vents": {}})
    sensor = FlairSystemSensor(coordinator, "entry")
    assert sensor.native_value == "hybrid"
    assert sensor.extra_state_attributes["last_strategy"] == "hybrid"
