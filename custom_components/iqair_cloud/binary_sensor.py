"""Binary sensor platform for IQAir Cloud."""
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE_IDS
from .coordinator import IQAirDataUpdateCoordinator
from .entity import IQAirEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IQAir binary sensor entities."""
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])

    async_add_entities(
        [IQAirConnectionStatus(coordinator, device_id) for device_id in device_ids]
    )


class IQAirConnectionStatus(IQAirEntity, BinarySensorEntity):
    """Representation of an IQAir device connection status."""

    _attr_name = "Connection Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_connection_status"

    @property
    def is_on(self) -> bool | None:
        """Return true if device is connected."""
        if not self.device_data:
            return None
        return self.device_data.get("isConnected")
