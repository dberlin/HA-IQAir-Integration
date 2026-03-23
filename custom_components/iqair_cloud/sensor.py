"""Sensor platform for IQAir Cloud."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_DEVICE_IDS
from .coordinator import IQAirDataUpdateCoordinator
from .entity import IQAirEntity

_LOGGER = logging.getLogger(__name__)

AQI_LABEL_OPTIONS = [
    "Good",
    "Moderate",
    "Unhealthy for Sensitive Groups",
    "Unhealthy",
    "Very Unhealthy",
    "Hazardous",
]

FILTER_LEVEL_OPTIONS = ["normal", "low"]

WEATHER_CONDITION_OPTIONS = [
    "Clear sky",
    "Few clouds",
    "Scattered clouds",
    "Broken clouds",
    "Shower rain",
    "Rain",
    "Thunderstorm",
    "Snow",
    "Mist",
]


@dataclass(frozen=True, kw_only=True)
class IQAirSensorDescription(SensorEntityDescription):
    """Describes an IQAir sensor entity."""

    value_path: tuple[str, ...]
    """Tuple of keys to traverse in device_data to get the value."""


# --- Indoor Air Quality Sensors ---
INDOOR_SENSOR_TYPES: tuple[IQAirSensorDescription, ...] = (
    IQAirSensorDescription(
        key="aqi",
        name="AQI",
        icon="mdi:air-filter",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("current", "aqi", "value"),
    ),
    IQAirSensorDescription(
        key="aqi_label",
        name="AQI Level",
        icon="mdi:air-filter",
        device_class=SensorDeviceClass.ENUM,
        options=AQI_LABEL_OPTIONS,
        value_path=("current", "aqi", "label"),
    ),
    IQAirSensorDescription(
        key="pm25",
        name="PM2.5",
        icon="mdi:blur",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("current", "pm25", "value"),
    ),
    IQAirSensorDescription(
        key="particle_count",
        name="Particle Count",
        icon="mdi:blur-radial",
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("current", "pc", "value"),
    ),
)

# --- Performance Sensors ---
PERFORMANCE_SENSOR_TYPES: tuple[IQAirSensorDescription, ...] = (
    IQAirSensorDescription(
        key="cadr_percent",
        name="Clean Air Delivery Rate",
        icon="mdi:fan-chevron-up",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("performance", "cleanAirDeliveryRatePercent"),
    ),
    IQAirSensorDescription(
        key="total_air_volume",
        name="Total Air Volume",
        icon="mdi:air-purifier",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_path=("performance", "totCumAirVolume"),
    ),
    IQAirSensorDescription(
        key="total_fan_runtime",
        name="Total Fan Runtime",
        icon="mdi:clock-outline",
        value_path=("performance", "totTimeFanRun"),
    ),
)

# --- Connectivity Sensor ---
CONNECTIVITY_SENSOR_TYPES: tuple[IQAirSensorDescription, ...] = (
    IQAirSensorDescription(
        key="wifi_signal",
        name="WiFi Signal",
        icon="mdi:wifi",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_path=("connectivity", "percentage"),
    ),
)


# --- Outdoor Sensors ---
@dataclass(frozen=True, kw_only=True)
class IQAirOutdoorSensorDescription(SensorEntityDescription):
    """Describes an IQAir outdoor sensor entity."""

    outdoor_key: str
    """Key within the outdoor dict to get the value."""


OUTDOOR_SENSOR_TYPES: tuple[IQAirOutdoorSensorDescription, ...] = (
    IQAirOutdoorSensorDescription(
        key="outdoor_aqi",
        name="AQI",
        icon="mdi:air-filter",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="aqi",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_pm25",
        name="PM2.5",
        icon="mdi:blur",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="pm25",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_temperature",
        name="Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="temperature",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_humidity",
        name="Humidity",
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="humidity",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_pressure",
        name="Pressure",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.INHG,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="pressure",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_wind_speed",
        name="Wind Speed",
        icon="mdi:weather-windy",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="wind_speed",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_wind_direction",
        name="Wind Direction",
        icon="mdi:compass",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        outdoor_key="wind_direction",
    ),
    IQAirOutdoorSensorDescription(
        key="outdoor_weather",
        name="Weather Condition",
        icon="mdi:weather-partly-cloudy",
        device_class=SensorDeviceClass.ENUM,
        options=WEATHER_CONDITION_OPTIONS,
        outdoor_key="condition",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IQAir sensor entities."""
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    device_ids = entry.data.get(CONF_DEVICE_IDS, [])
    entities: list[SensorEntity] = []

    for device_id in device_ids:
        device_data = (coordinator.data or {}).get("devices", {}).get(device_id, {})

        # Indoor air quality sensors
        for description in INDOOR_SENSOR_TYPES:
            entities.append(
                IQAirSensor(coordinator, device_id, description)
            )

        # Performance sensors
        for description in PERFORMANCE_SENSOR_TYPES:
            entities.append(
                IQAirSensor(coordinator, device_id, description)
            )

        # Connectivity sensors
        for description in CONNECTIVITY_SENSOR_TYPES:
            entities.append(
                IQAirSensor(coordinator, device_id, description)
            )

        # Filter sensors — dynamic based on filter count
        filters = device_data.get("remote", {}).get("filters", [])
        for filter_data in filters:
            slot = filter_data.get("slot", 0)
            mediums = filter_data.get("filterMediums", [])
            filter_name = mediums[0] if mediums else f"Filter {slot}"

            # Filter health sensor
            entities.append(
                IQAirFilterSensor(
                    coordinator,
                    device_id,
                    slot,
                    filter_name,
                    sensor_type="health",
                )
            )
            # Filter level sensor
            entities.append(
                IQAirFilterSensor(
                    coordinator,
                    device_id,
                    slot,
                    filter_name,
                    sensor_type="level",
                )
            )

    # Outdoor sensors — deduplicated by location ID
    seen_locations: set[str] = set()
    for device_id in sorted(device_ids):
        device_data = (coordinator.data or {}).get("devices", {}).get(device_id, {})
        outdoor = device_data.get("current", {}).get("outdoor", {})
        location_id = outdoor.get("id")
        if location_id and location_id not in seen_locations:
            seen_locations.add(location_id)
            city = outdoor.get("city", "Unknown")
            for description in OUTDOOR_SENSOR_TYPES:
                entities.append(
                    IQAirOutdoorSensor(
                        coordinator, location_id, city, description
                    )
                )

    async_add_entities(entities)


class IQAirSensor(IQAirEntity, SensorEntity):
    """Representation of an IQAir sensor."""

    entity_description: IQAirSensorDescription
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        device_id: str,
        description: IQAirSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        data = self.device_data
        if not data:
            return None
        # Traverse the value path
        value = data
        for key in self.entity_description.value_path:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


class IQAirFilterSensor(IQAirEntity, SensorEntity):
    """Representation of an IQAir filter sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        device_id: str,
        slot: int,
        filter_name: str,
        sensor_type: str,
    ) -> None:
        """Initialize the filter sensor."""
        super().__init__(coordinator, device_id)
        self._slot = slot
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{device_id}_filter_{slot}_{sensor_type}"

        self._filter_name_fallback = filter_name
        if sensor_type == "health":
            self._attr_icon = "mdi:air-filter"
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:  # level
            self._attr_icon = "mdi:alert-circle-outline"
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = FILTER_LEVEL_OPTIONS

    @property
    def name(self) -> str:
        """Return the name, using live filter medium name when available."""
        filter_data = self._get_filter_data()
        if filter_data:
            mediums = filter_data.get("filterMediums", [])
            filter_name = mediums[0] if mediums else self._filter_name_fallback
        else:
            filter_name = self._filter_name_fallback
        suffix = "Health" if self._sensor_type == "health" else "Level"
        return f"{filter_name} {suffix}"

    def _get_filter_data(self) -> dict | None:
        """Get the filter data for this slot."""
        filters = self.device_data.get("remote", {}).get("filters", [])
        for f in filters:
            if f.get("slot") == self._slot:
                return f
        return None

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        filter_data = self._get_filter_data()
        if filter_data is None:
            return None
        if self._sensor_type == "health":
            return filter_data.get("healthPercent")
        return filter_data.get("filterLevel")


class IQAirOutdoorSensor(CoordinatorEntity[IQAirDataUpdateCoordinator], SensorEntity):
    """Representation of an IQAir outdoor sensor."""

    entity_description: IQAirOutdoorSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        location_id: str,
        city: str,
        description: IQAirOutdoorSensorDescription,
    ) -> None:
        """Initialize the outdoor sensor."""
        super().__init__(coordinator)
        self._location_id = location_id
        self.entity_description = description
        self._attr_unique_id = f"{location_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the outdoor location."""
        outdoor = (self.coordinator.data or {}).get("outdoor_locations", {}).get(
            self._location_id, {}
        )
        city = outdoor.get("city", "Unknown")
        return DeviceInfo(
            identifiers={(DOMAIN, f"outdoor_{self._location_id}")},
            name=f"{city} Outdoor Air Quality",
            manufacturer="IQAir",
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        outdoor = (self.coordinator.data or {}).get("outdoor_locations", {}).get(
            self._location_id, {}
        )
        if not outdoor:
            return None

        key = self.entity_description.outdoor_key
        if key == "wind_speed":
            return outdoor.get("wind", {}).get("speed")
        if key == "wind_direction":
            return outdoor.get("wind", {}).get("direction")
        return outdoor.get(key)
