"""Select platform for IQAir Cloud."""
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IDS, AUTO_MODE_PROFILE_MAP, LIGHT_LEVEL_MAP
from .api import IQAirApiClient
from .coordinator import IQAirDataUpdateCoordinator
from .entity import IQAirEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IQAir select entities."""
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    api_client: IQAirApiClient = hass.data[DOMAIN][entry.entry_id]["api_client"]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])

    entities = []
    for device_id in device_ids:
        entities.append(
            IQAirAutoModeProfileSelect(coordinator, api_client, device_id)
        )
        entities.append(
            IQAirLightLevelSelect(coordinator, api_client, device_id)
        )
    async_add_entities(entities)


class IQAirAutoModeProfileSelect(IQAirEntity, SelectEntity):
    """Representation of an IQAir Cloud auto mode profile select entity."""

    _attr_name = "Smart Mode Profile"
    _attr_icon = "mdi:tune"
    _attr_should_poll = False
    _attr_options = list(AUTO_MODE_PROFILE_MAP.values())

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        api_client: IQAirApiClient,
        device_id: str,
    ):
        """Initialize the select entity."""
        super().__init__(coordinator, device_id)
        self._api = api_client
        self._attr_unique_id = f"{device_id}_auto_mode_profile"

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if not self.available or not self.device_data:
            return None
        profile_id = self.device_data.get("remote", {}).get("autoModeProfile")
        return AUTO_MODE_PROFILE_MAP.get(profile_id)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        profile_id = next(
            (k for k, v in AUTO_MODE_PROFILE_MAP.items() if v == option), None
        )
        if profile_id is not None:
            update_data = await self._api.set_auto_mode_profile(
                profile_id,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
            if update_data is not None:
                self.coordinator.update_from_command(self._device_id, update_data)


class IQAirLightLevelSelect(IQAirEntity, SelectEntity):
    """Representation of an IQAir Cloud light level select entity."""

    _attr_name = "Display Brightness"
    _attr_icon = "mdi:brightness-6"
    _attr_should_poll = False
    _attr_options = list(LIGHT_LEVEL_MAP.values())

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        api_client: IQAirApiClient,
        device_id: str,
    ):
        """Initialize the select entity."""
        super().__init__(coordinator, device_id)
        self._api = api_client
        self._attr_unique_id = f"{device_id}_light_level"

    @property
    def current_option(self) -> str | None:
        """Return the selected option."""
        if not self.available or not self.device_data:
            return None
        level_id = self.device_data.get("remote", {}).get("lightLevel")
        return LIGHT_LEVEL_MAP.get(level_id)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        level_id = next(
            (k for k, v in LIGHT_LEVEL_MAP.items() if v == option), None
        )
        if level_id is not None:
            update_data = await self._api.set_light_level(
                level_id,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
            if update_data is not None:
                self.coordinator.update_from_command(self._device_id, update_data)
