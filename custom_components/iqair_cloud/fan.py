"""Fan platform for IQAir Cloud."""
import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IDS
from .api import IQAirApiClient
from .coordinator import IQAirDataUpdateCoordinator
from .entity import IQAirEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IQAir fan entities."""
    api_client: IQAirApiClient = hass.data[DOMAIN][entry.entry_id]["api_client"]
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])

    # Migrate old unique IDs: {device_id} → {device_id}_fan
    ent_reg = er.async_get(hass)
    for device_id in device_ids:
        old_unique_id = device_id
        new_unique_id = f"{device_id}_fan"
        existing = ent_reg.async_get_entity_id("fan", DOMAIN, old_unique_id)
        if existing:
            _LOGGER.info(
                "Migrating fan entity unique_id from %s to %s",
                old_unique_id,
                new_unique_id,
            )
            ent_reg.async_update_entity(existing, new_unique_id=new_unique_id)

    async_add_entities(
        [IQAirFan(coordinator, api_client, device_id) for device_id in device_ids]
    )


class IQAirFan(IQAirEntity, FanEntity):
    """Representation of an IQAir Cloud fan."""

    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        api_client: IQAirApiClient,
        device_id: str,
    ):
        """Initialize the fan."""
        super().__init__(coordinator, device_id)
        self._api = api_client
        self._attr_unique_id = f"{device_id}_fan"

    @property
    def _is_percentage_control(self) -> bool:
        """Return True if device uses percentage control."""
        return self.device_data.get("featureSet", {}).get(
            "isFanSpeedControlInPercent", False
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the fan is on."""
        if not self.available or not self.device_data:
            return None
        return self.device_data.get("remote", {}).get("powerMode") == 2

    @property
    def percentage(self) -> int | None:
        """Return the current speed percentage."""
        if not self.available or not self.device_data:
            return None
        return self.device_data.get("remote", {}).get("speedPercent")

    @property
    def percentage_step(self) -> float:
        """Return the step size for percentage."""
        if self._is_percentage_control:
            return 1.0
        return super().percentage_step

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        if self._is_percentage_control:
            return 100
        if self.device_data:
            return self.device_data.get("remote", {}).get("maxSpeedLevel", 1)
        return 1

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            update_data = await self._api.set_power(
                True,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
                context="fan.turn_on",
            )
            if update_data is not None:
                self.coordinator.update_from_command(self._device_id, update_data)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        update_data = await self._api.set_power(
            False,
            serial_number=self._serial_number,
            device_prefix=self._device_prefix,
            endpoint_service=self._endpoint_service,
            context="fan.turn_off",
        )
        if update_data is not None:
            self.coordinator.update_from_command(self._device_id, update_data)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return

        update_data = None
        if self._is_percentage_control:
            update_data = await self._api.set_fan_speed_percent(
                percentage,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
                context="fan.set_percentage",
            )
        else:
            speed_level = math.ceil(percentage / 100 * self.speed_count)
            speed_level = max(1, min(self.speed_count, speed_level))
            update_data = await self._api.set_fan_speed(
                speed_level,
                serial_number=self._serial_number,
                device_prefix=self._device_prefix,
                endpoint_service=self._endpoint_service,
                context="fan.set_percentage",
            )

        if update_data is not None:
            if not self._is_percentage_control:
                speed_level_from_api = update_data.get("speedLevel")
                if speed_level_from_api and self.device_data:
                    man_speed_table = self.device_data.get("remote", {}).get(
                        "manSpeedTable", []
                    )
                    if (
                        isinstance(man_speed_table, list)
                        and 0 < speed_level_from_api <= len(man_speed_table)
                    ):
                        update_data["speedPercent"] = man_speed_table[
                            speed_level_from_api - 1
                        ]

            self.coordinator.update_from_command(self._device_id, update_data)
