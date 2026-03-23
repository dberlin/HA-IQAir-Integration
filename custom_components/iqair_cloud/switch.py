"""Switch platform for IQAir Cloud."""
import logging
from typing import Any
from dataclasses import dataclass

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IDS
from .api import IQAirApiClient
from .coordinator import IQAirDataUpdateCoordinator
from .entity import IQAirEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class IQAirSwitchEntityDescription(SwitchEntityDescription):
    """Describes an IQAir switch entity."""

    state_key: str


SWITCH_TYPES: tuple[IQAirSwitchEntityDescription, ...] = (
    IQAirSwitchEntityDescription(
        key="auto_mode",
        name="Smart Mode",
        icon="mdi:fan-auto",
        state_key="autoModeEnabled",
    ),
    IQAirSwitchEntityDescription(
        key="control_panel_lock",
        name="Control Panel Lock",
        icon="mdi:lock",
        state_key="isLocksEnabled",
    ),
    IQAirSwitchEntityDescription(
        key="display_light",
        name="Display Light",
        icon="mdi:lightbulb",
        state_key="lightIndicatorEnabled",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IQAir switch entities."""
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    api_client: IQAirApiClient = hass.data[DOMAIN][entry.entry_id]["api_client"]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])

    entities = [
        IQAirSwitch(coordinator, api_client, device_id, description)
        for device_id in device_ids
        for description in SWITCH_TYPES
    ]
    async_add_entities(entities)


class IQAirSwitch(IQAirEntity, SwitchEntity):
    """Representation of an IQAir Cloud switch."""

    entity_description: IQAirSwitchEntityDescription
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        api_client: IQAirApiClient,
        device_id: str,
        description: IQAirSwitchEntityDescription,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, device_id)
        self._api = api_client
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        if not self.available or not self.device_data:
            return None
        return self.device_data.get("remote", {}).get(
            self.entity_description.state_key
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        update_data = None
        if self.entity_description.key == "auto_mode":
            update_data = await self._api.set_auto_mode(
                True,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
        elif self.entity_description.key == "control_panel_lock":
            update_data = await self._api.set_lock(
                True,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
        elif self.entity_description.key == "display_light":
            update_data = await self._api.set_light_indicator(
                True,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )

        if update_data is not None:
            self.coordinator.update_from_command(self._device_id, update_data)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        update_data = None
        if self.entity_description.key == "auto_mode":
            update_data = await self._api.set_auto_mode(
                False,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
        elif self.entity_description.key == "control_panel_lock":
            update_data = await self._api.set_lock(
                False,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )
        elif self.entity_description.key == "display_light":
            update_data = await self._api.set_light_indicator(
                False,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
            )

        if update_data is not None:
            self.coordinator.update_from_command(self._device_id, update_data)
