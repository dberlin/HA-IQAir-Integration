"""Base entity for the IQAir Cloud integration."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL_SERVICE_MAP
from .coordinator import IQAirDataUpdateCoordinator


class IQAirEntity(CoordinatorEntity[IQAirDataUpdateCoordinator]):
    """Base class for IQAir entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id

    @property
    def device_data(self) -> dict:
        """Return the device data from the coordinator."""
        return (self.coordinator.data or {}).get("devices", {}).get(self._device_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the device registry."""
        data = self.device_data
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=data.get("name", "IQAir Device"),
            manufacturer="IQAir",
            model=data.get("modelLabel"),
            sw_version=data.get("modelVariation"),
        )

    @property
    def _serial_number(self) -> str:
        """Return the serial number for this device."""
        return self.device_data.get("serialNumber", "")

    @property
    def _device_prefix(self) -> str:
        """Return the device prefix based on model."""
        model = self.device_data.get("model", "ui2")
        return MODEL_SERVICE_MAP.get(model, MODEL_SERVICE_MAP["ui2"])["prefix"]

    @property
    def _endpoint_service(self) -> str:
        """Return the gRPC endpoint service based on model."""
        model = self.device_data.get("model", "ui2")
        return MODEL_SERVICE_MAP.get(model, MODEL_SERVICE_MAP["ui2"])["endpoint"]
