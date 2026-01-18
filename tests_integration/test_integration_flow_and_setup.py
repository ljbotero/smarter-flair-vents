from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

DOMAIN = "smarter_flair_vents"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_STRUCTURE_ID = "structure_id"


@pytest.mark.asyncio
async def test_config_flow_creates_entry(hass, fake_api):
    with patch(
        "custom_components.smarter_flair_vents.config_flow.FlairApi",
        return_value=fake_api,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == "form"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret"},
        )
        assert result2["type"] == "create_entry"
        assert result2["data"][CONF_STRUCTURE_ID] == "structure1"


@pytest.mark.asyncio
async def test_setup_creates_room_device_and_entities(hass, fake_api):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CLIENT_ID: "id",
            CONF_CLIENT_SECRET: "secret",
            CONF_STRUCTURE_ID: "structure1",
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.smarter_flair_vents.FlairApi", return_value=fake_api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    room_device = next(
        device
        for device in device_registry.devices.values()
        if (DOMAIN, "room_room1") in device.identifiers
    )

    room_entities = [
        entry
        for entry in entity_registry.entities.values()
        if entry.device_id == room_device.id
    ]

    assert any(entry.domain == "switch" for entry in room_entities)
    assert any(entry.domain == "climate" for entry in room_entities)
    assert any(entry.domain == "sensor" for entry in room_entities)
