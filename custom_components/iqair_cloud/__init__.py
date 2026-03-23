"""The IQAir Cloud integration."""
from __future__ import annotations
from typing import Any

import httpx
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import IQAirApiClient
from .const import (
    DOMAIN,
    CONF_LOGIN_TOKEN,
    CONF_USER_ID,
    CONF_AUTH_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_IDS,
    CONF_SERIAL_NUMBER,
    CONF_API_ENDPOINT,
    CONF_DEVICE_PREFIX,
    GRPC_API_HEADERS,
)
from .coordinator import IQAirDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.FAN,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format."""
    if config_entry.version == 1:
        _LOGGER.info("Migrating IQAir config entry from version 1 to 2")
        new_data = {**config_entry.data}

        # Migrate single device ID to list
        old_device_id = new_data.pop(CONF_DEVICE_ID, None)
        new_data.pop(CONF_SERIAL_NUMBER, None)
        new_data.pop(CONF_API_ENDPOINT, None)
        new_data.pop(CONF_DEVICE_PREFIX, None)

        if old_device_id:
            new_data[CONF_DEVICE_IDS] = [old_device_id]
        else:
            new_data[CONF_DEVICE_IDS] = []

        hass.config_entries.async_update_entry(
            config_entry, version=2, data=new_data
        )
        _LOGGER.info("Migration to version 2 successful")
        return True

    if config_entry.version >= 2:
        return True

    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IQAir Cloud from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    login_token = entry.data[CONF_LOGIN_TOKEN]
    user_id = entry.data[CONF_USER_ID]
    auth_token = entry.data[CONF_AUTH_TOKEN]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])

    def _create_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
        """Create the httpx clients in a thread-safe way."""
        command_client = httpx.AsyncClient(
            http2=True,
            headers={**GRPC_API_HEADERS, "Authorization": f"Bearer {auth_token}"},
        )
        state_client = httpx.AsyncClient(headers={"x-login-token": login_token})
        return command_client, state_client

    command_client, state_client = await hass.async_add_executor_job(_create_clients)

    api_client = IQAirApiClient(
        command_client=command_client,
        state_client=state_client,
        user_id=user_id,
    )

    coordinator = IQAirDataUpdateCoordinator(
        hass, api=api_client, device_ids=device_ids
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "api_client": api_client,
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.add_update_listener(update_listener)

    async def async_close_clients() -> None:
        """Close the httpx clients."""
        await command_client.aclose()
        await state_client.aclose()

    entry.async_on_unload(async_close_clients)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
