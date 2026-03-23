"""Data update coordinator for the IQAir Cloud integration."""
from typing import Any
import copy
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .api import IQAirApiClient
from .exceptions import InvalidAuth

_LOGGER = logging.getLogger(__name__)


class IQAirDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching IQAir data."""

    def __init__(
        self, hass: HomeAssistant, api: IQAirApiClient, device_ids: list[str]
    ):
        """Initialize."""
        self.api = api
        self.device_ids = device_ids
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            all_devices = await self.api.async_get_devices()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err

        if not all_devices:
            raise UpdateFailed("No devices returned from API")

        # Build devices dict keyed by device ID, filtered to selected devices
        devices = {}
        for device in all_devices:
            device_id = device.get("id")
            if device_id in self.device_ids:
                devices[device_id] = device

        if not devices:
            raise UpdateFailed("Selected devices not found in API response")

        # Build outdoor locations dict, deduplicated by location ID
        # Iterate in sorted order for deterministic source selection
        outdoor_locations = {}
        for device_id in sorted(devices.keys()):
            device = devices[device_id]
            outdoor = device.get("current", {}).get("outdoor", {})
            location_id = outdoor.get("id")
            if location_id and location_id not in outdoor_locations:
                outdoor_locations[location_id] = outdoor

        return {
            "devices": devices,
            "outdoor_locations": outdoor_locations,
        }

    def update_from_command(self, device_id: str, update_data: dict[str, Any]):
        """Update coordinator data from a command response."""
        if self.data and update_data and device_id in self.data.get("devices", {}):
            new_data = copy.deepcopy(self.data)
            new_data["devices"][device_id].setdefault("remote", {}).update(update_data)
            self.async_set_updated_data(new_data)
