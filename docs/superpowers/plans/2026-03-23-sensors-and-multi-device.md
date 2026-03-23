# IQAir Sensors & Multi-Device Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sensor entities for all API data (AQI, PM2.5, filters, performance, connectivity, outdoor weather) and refactor the integration from single-device to multi-device support.

**Architecture:** Single coordinator polls the all-devices endpoint, stores data keyed by device ID. A base entity class provides device lookup for all platforms. New sensor.py and binary_sensor.py files define read-only entities. Config flow changes from single-device dropdown to multi-select checkboxes.

**Tech Stack:** Home Assistant custom integration (Python), httpx, DataUpdateCoordinator pattern.

**Note:** This project has no test infrastructure. Steps include manual verification guidance instead of automated tests. Each task ends with a commit.

**Spec:** `docs/superpowers/specs/2026-03-23-sensors-and-multi-device-design.md`

---

## Chunk 1: Foundation Layer

### Task 1: Update constants

**Files:**
- Modify: `custom_components/iqair_cloud/const.py`

- [ ] **Step 1: Add new constants to const.py**

Add `CONF_DEVICE_IDS`, model-to-prefix/endpoint mapping, and mark `CONF_DEVICE_ID` as deprecated:

```python
# After existing CONF_ constants (line 14-17), add:

CONF_DEVICE_IDS: Final = "device_ids"  # v2: list of selected device IDs

# Deprecated - kept for v1→v2 config migration only
# CONF_DEVICE_ID (line 14) - already exists, add comment above it:
# CONF_DEVICE_ID: Final = "device_id"  # Deprecated: used for v1→v2 migration only
# CONF_SERIAL_NUMBER (line 15) - already exists, add comment above it
# CONF_API_ENDPOINT (line 16) - already exists, add comment above it
# CONF_DEVICE_PREFIX (line 17) - already exists, add comment above it

# --- Model-to-Service Mapping ---
MODEL_SERVICE_MAP: Final = {
    "ui2": {"prefix": "UI2", "endpoint": API_SERVICE_UI2},
    "klr": {"prefix": "KLR", "endpoint": API_SERVICE_KLR},
}
```

- [ ] **Step 2: Verify the file is valid Python**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/const.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/const.py
git commit -m "feat: add multi-device constants and model-to-service mapping"
```

---

### Task 2: Refactor API client to accept per-command serial numbers

**Files:**
- Modify: `custom_components/iqair_cloud/api.py`

The API client currently stores `_serial_number`, `_endpoint`, and `_device_prefix` as instance state. These must become per-command parameters since different devices may have different models/prefixes.

- [ ] **Step 1: Update constructor — remove device-specific params**

Change `__init__` from:
```python
def __init__(
    self,
    command_client: httpx.AsyncClient,
    state_client: httpx.AsyncClient,
    user_id: str,
    serial_number: str | None,
    endpoint: str,
    device_prefix: str,
):
    self._user_id = user_id
    self._command_client = command_client
    self._state_client = state_client
    self._serial_number = serial_number
    self._endpoint = endpoint
    self._device_prefix = device_prefix
```

To:
```python
def __init__(
    self,
    command_client: httpx.AsyncClient,
    state_client: httpx.AsyncClient,
    user_id: str,
):
    self._user_id = user_id
    self._command_client = command_client
    self._state_client = state_client
```

- [ ] **Step 2: Update `_build_payload` to accept serial_number and device_prefix params**

Change from:
```python
def _build_payload(self, field: int, value: int | None = None) -> str:
    if not self._serial_number:
        raise ValueError("Serial number is not set")
    prefix = f"{self._device_prefix}_"
    sn_part = self._serial_number.replace(prefix, "").lower().encode("utf-8")
```

To:
```python
def _build_payload(self, serial_number: str, device_prefix: str, field: int, value: int | None = None) -> str:
    prefix = f"{device_prefix}_"
    sn_part = serial_number.replace(prefix, "").lower().encode("utf-8")
```

- [ ] **Step 3: Update `_send_command` to accept endpoint_service param**

Change from:
```python
async def _send_command(
    self, endpoint: str, payload: str, context: str | None = None
) -> dict[str, Any] | None:
    url = f"{GRPC_API_BASE_URL}{self._endpoint}{endpoint}"
```

To:
```python
async def _send_command(
    self, endpoint_service: str, endpoint: str, payload: str, context: str | None = None
) -> dict[str, Any] | None:
    url = f"{GRPC_API_BASE_URL}{endpoint_service}{endpoint}"
```

- [ ] **Step 4: Update all command methods to accept serial_number, device_prefix, endpoint_service**

Each command method (`set_power`, `set_fan_speed`, `set_fan_speed_percent`, `set_light_indicator`, `set_light_level`, `set_auto_mode`, `set_auto_mode_profile`, `set_lock`) gets three new required parameters: `serial_number: str`, `device_prefix: str`, `endpoint_service: str`.

Example for `set_power`:
```python
async def set_power(
    self, is_on: bool, serial_number: str, device_prefix: str, endpoint_service: str, context: str | None = None
) -> dict[str, Any] | None:
    value = 2 if is_on else 3
    payload = self._build_payload(serial_number, device_prefix, FIELD_POWER, value)
    return await self._send_command(endpoint_service, ENDPOINT_POWER, payload, context=context)
```

Apply the same pattern to all 8 command methods. Each one:
1. Adds `serial_number: str, device_prefix: str, endpoint_service: str` params
2. Passes `serial_number, device_prefix` to `self._build_payload(...)`
3. Passes `endpoint_service` as first arg to `self._send_command(...)`

- [ ] **Step 4b: Fix pre-existing bug in `async_get_cloud_api_auth_token`**

In the standalone function `async_get_cloud_api_auth_token`, `httpx.Response.text` is a property, not a coroutine. Fix two lines:

Change `html_content = await response.text()` to `html_content = response.text`
Change `js_content = await response.text()` to `js_content = response.text`

Also fix the same class of bug in `async_signin`:
Change `return await response.json()` to `return response.json()`

- [ ] **Step 5: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/api.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add custom_components/iqair_cloud/api.py
git commit -m "refactor: api client accepts per-command serial number and endpoint"
```

---

### Task 3: Create base entity class

**Files:**
- Create: `custom_components/iqair_cloud/entity.py`

- [ ] **Step 1: Write the base entity class**

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/entity.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/entity.py
git commit -m "feat: add IQAirEntity base class with device data lookup"
```

---

### Task 4: Refactor coordinator for multi-device

**Files:**
- Modify: `custom_components/iqair_cloud/coordinator.py`

- [ ] **Step 1: Rewrite coordinator for multi-device data structure**

Replace the entire file:

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/coordinator.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/coordinator.py
git commit -m "refactor: coordinator supports multi-device data structure"
```

---

### Task 5: Update `__init__.py` for multi-device setup and config migration

**Files:**
- Modify: `custom_components/iqair_cloud/__init__.py`

- [ ] **Step 1: Rewrite `__init__.py`**

Replace the entire file:

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/__init__.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/__init__.py
git commit -m "feat: add config migration v1→v2 and multi-device setup"
```

---

## Chunk 2: Refactor Existing Entity Platforms

### Task 6: Refactor fan.py for multi-device and base entity

**Files:**
- Modify: `custom_components/iqair_cloud/fan.py`

- [ ] **Step 1: Rewrite fan.py**

Key changes:
- Inherit from `IQAirEntity` instead of bare `FanEntity`
- Create one fan per selected device
- Use `self.device_data` instead of `self.coordinator.data`
- Pass `device_id` to `update_from_command`
- Pass serial number, prefix, and endpoint to API commands
- Migrate entity unique ID from `{device_id}` to `{device_id}_fan`

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/fan.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/fan.py
git commit -m "refactor: fan entity uses base class, supports multi-device"
```

---

### Task 7: Refactor switch.py for multi-device and base entity

**Files:**
- Modify: `custom_components/iqair_cloud/switch.py`

- [ ] **Step 1: Rewrite switch.py**

Key changes:
- Inherit from `IQAirEntity` and `SwitchEntity`
- Create switches for each selected device
- Use `self.device_data` for state
- Pass device ID to `update_from_command`
- Pass serial number/prefix/endpoint to API commands

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/switch.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/switch.py
git commit -m "refactor: switch entity uses base class, supports multi-device"
```

---

### Task 8: Refactor select.py for multi-device and base entity

**Files:**
- Modify: `custom_components/iqair_cloud/select.py`

- [ ] **Step 1: Rewrite select.py**

Key changes:
- Inherit from `IQAirEntity` and `SelectEntity`
- Create select entities for each selected device
- Use `self.device_data` for state
- Pass device ID to `update_from_command`
- Pass serial number/prefix/endpoint to API commands

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/select.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/select.py
git commit -m "refactor: select entity uses base class, supports multi-device"
```

---

## Chunk 3: New Sensor Entities

### Task 9: Create sensor.py with all sensor entity types

**Files:**
- Create: `custom_components/iqair_cloud/sensor.py`

- [ ] **Step 1: Write the sensor platform**

This file contains indoor air quality sensors, filter sensors, performance sensors, WiFi signal sensor, and outdoor sensors.

```python
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

        if sensor_type == "health":
            self._attr_name = f"{filter_name} Health"
            self._attr_icon = "mdi:air-filter"
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:  # level
            self._attr_name = f"{filter_name} Level"
            self._attr_icon = "mdi:alert-circle-outline"
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = FILTER_LEVEL_OPTIONS

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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/sensor.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/sensor.py
git commit -m "feat: add sensor entities for AQI, filters, performance, outdoor"
```

---

### Task 10: Create binary_sensor.py for connection status

**Files:**
- Create: `custom_components/iqair_cloud/binary_sensor.py`

- [ ] **Step 1: Write the binary sensor platform**

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/binary_sensor.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/binary_sensor.py
git commit -m "feat: add connection status binary sensor"
```

---

## Chunk 4: Config Flow & Translations

### Task 11: Rewrite config_flow.py for multi-device selection

**Files:**
- Modify: `custom_components/iqair_cloud/config_flow.py`

- [ ] **Step 1: Rewrite the config flow**

Key changes:
- `VERSION = 2`
- Config entry unique ID uses `user_id` instead of `device_id`
- `async_step_select_device` → `async_step_select_devices` with multi-select
- Options flow replaced with device selection
- Re-auth flow uses dedicated `async_step_reauth_confirm`
- `validate_connection` updated for new API client constructor

```python
"""Config flow for IQAir Cloud."""
import logging
from typing import Any

import httpx
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_LOGIN_TOKEN,
    CONF_USER_ID,
    CONF_AUTH_TOKEN,
    CONF_DEVICE_IDS,
)
from .api import IQAirApiClient, async_signin, async_get_cloud_api_auth_token
from .exceptions import CannotConnect, InvalidAuth, NoDevicesFound

_LOGGER = logging.getLogger(__name__)


async def create_state_client(hass: HomeAssistant, login_token: str) -> httpx.AsyncClient:
    """Create the httpx state client in a thread-safe way."""

    def _create_client() -> httpx.AsyncClient:
        """Create the httpx client."""
        return httpx.AsyncClient(headers={"x-login-token": login_token})

    return await hass.async_add_executor_job(_create_client)


async def validate_connection(
    hass: HomeAssistant, login_token: str, user_id: str
) -> list[dict[str, Any]]:
    """Validate the user input allows us to connect."""
    state_client = await create_state_client(hass, login_token)
    api_client = IQAirApiClient(
        command_client=None,
        state_client=state_client,
        user_id=user_id,
    )

    try:
        devices = await api_client.async_get_devices()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise InvalidAuth from exc
        raise CannotConnect from exc
    except httpx.RequestError as exc:
        raise CannotConnect from exc
    finally:
        await state_client.aclose()

    if not devices:
        raise NoDevicesFound

    return devices


def _build_device_selector(devices: list[dict[str, Any]]) -> SelectSelector:
    """Build a multi-select selector for device selection."""
    options = [
        SelectOptionDict(value=dev["id"], label=dev["name"])
        for dev in devices
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


class AuthResult:
    """Result of an authentication attempt."""

    def __init__(self, tokens: dict[str, Any] | None = None, error: str = "invalid_auth"):
        self.tokens = tokens
        self.error = error

    @property
    def success(self) -> bool:
        return self.tokens is not None


async def _do_auth_credentials(hass: HomeAssistant, user_input: dict[str, Any]) -> AuthResult:
    """Perform credentials-based authentication."""
    session = async_get_clientsession(hass)
    signin_data = await async_signin(
        session, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
    )
    if not signin_data:
        return AuthResult(error="invalid_auth")

    auth_token = await async_get_cloud_api_auth_token(session)
    if not auth_token:
        return AuthResult(error="cannot_connect")

    return AuthResult(tokens={
        CONF_LOGIN_TOKEN: signin_data["loginToken"],
        CONF_USER_ID: signin_data["id"],
        CONF_AUTH_TOKEN: auth_token,
    })


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IQAir Cloud."""

    VERSION = 2
    _user_input: dict[str, Any] = {}
    _devices: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "IQAirOptionsFlowHandler":
        """Get the options flow for this handler."""
        return IQAirOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step to choose auth method."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["credentials", "tokens"],
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the email and password step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await _do_auth_credentials(self.hass, user_input)
            if not result.success:
                errors["base"] = result.error
            else:
                self._user_input.update(result.tokens)
                try:
                    self._devices = await validate_connection(
                        self.hass,
                        self._user_input[CONF_LOGIN_TOKEN],
                        self._user_input[CONF_USER_ID],
                    )
                    return await self.async_step_select_devices()
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except NoDevicesFound:
                    errors["base"] = "no_devices"

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_tokens(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the manual token entry step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._user_input = user_input
            try:
                self._devices = await validate_connection(
                    self.hass, user_input[CONF_LOGIN_TOKEN], user_input[CONF_USER_ID]
                )
                return await self.async_step_select_devices()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except NoDevicesFound:
                errors["base"] = "no_devices"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="tokens",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOGIN_TOKEN): str,
                    vol.Required(CONF_USER_ID): str,
                    vol.Required(CONF_AUTH_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the device selection step (multi-select)."""
        if user_input is not None:
            selected_ids = user_input.get(CONF_DEVICE_IDS, [])
            if not selected_ids:
                return self.async_show_form(
                    step_id="select_devices",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_DEVICE_IDS): _build_device_selector(self._devices),
                        }
                    ),
                    errors={"base": "no_devices"},
                )

            # Use user_id as the unique ID for the config entry
            await self.async_set_unique_id(self._user_input[CONF_USER_ID])
            self._abort_if_unique_id_configured()

            # Use the first selected device's name as the entry title
            first_device = next(
                (d for d in self._devices if d["id"] == selected_ids[0]), None
            )
            title = first_device["name"] if first_device else "IQAir"
            if len(selected_ids) > 1:
                title = f"IQAir ({len(selected_ids)} devices)"

            data = {
                **self._user_input,
                CONF_DEVICE_IDS: selected_ids,
            }

            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="select_devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_IDS): _build_device_selector(self._devices),
                }
            ),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show re-auth menu."""
        return self.async_show_menu(
            step_id="reauth_confirm",
            menu_options=["reauth_credentials", "reauth_tokens"],
        )

    async def async_step_reauth_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-auth via email and password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await _do_auth_credentials(self.hass, user_input)
            if not result.success:
                errors["base"] = result.error
            else:
                existing_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={**existing_entry.data, **result.tokens},
                )
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth_tokens(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-auth via manual tokens."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_connection(
                    self.hass, user_input[CONF_LOGIN_TOKEN], user_input[CONF_USER_ID]
                )
            except (CannotConnect, InvalidAuth, NoDevicesFound):
                errors["base"] = "invalid_auth"
            else:
                existing_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                self.hass.config_entries.async_update_entry(
                    existing_entry,
                    data={
                        **existing_entry.data,
                        CONF_AUTH_TOKEN: user_input[CONF_AUTH_TOKEN],
                        CONF_LOGIN_TOKEN: user_input[CONF_LOGIN_TOKEN],
                        CONF_USER_ID: user_input[CONF_USER_ID],
                    },
                )
                await self.hass.config_entries.async_reload(existing_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_tokens",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOGIN_TOKEN): str,
                    vol.Required(CONF_USER_ID): str,
                    vol.Required(CONF_AUTH_TOKEN): str,
                }
            ),
            errors=errors,
        )


class IQAirOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for IQAir Cloud."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options — device selection."""
        if user_input is not None:
            selected_ids = user_input[CONF_DEVICE_IDS]

            # Update the config entry data with new device selection
            new_data = {**self.config_entry.data, CONF_DEVICE_IDS: selected_ids}
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

            return self.async_create_entry(title="", data={})

        # Fetch current devices from API
        login_token = self.config_entry.data[CONF_LOGIN_TOKEN]
        user_id = self.config_entry.data[CONF_USER_ID]

        try:
            devices = await validate_connection(self.hass, login_token, user_id)
        except (CannotConnect, InvalidAuth, NoDevicesFound):
            return self.async_abort(reason="cannot_connect")

        current_ids = self.config_entry.data.get(CONF_DEVICE_IDS, [])

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_IDS, default=current_ids
                    ): _build_device_selector(devices),
                }
            ),
        )
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('custom_components/iqair_cloud/config_flow.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/iqair_cloud/config_flow.py
git commit -m "refactor: config flow with multi-device selection and v2 schema"
```

---

### Task 12: Update translations and manifest

**Files:**
- Modify: `custom_components/iqair_cloud/translations/en.json`
- Modify: `custom_components/iqair_cloud/manifest.json`

- [ ] **Step 1: Update translations/en.json**

Replace the entire file:

```json
{
  "config": {
    "step": {
      "user": {
        "menu_options": {
          "credentials": "Email and Password",
          "tokens": "Manual Tokens"
        },
        "menu_option_descriptions": {
          "credentials": "The recommended method. The integration will sign in with your email and password to get the necessary tokens.",
          "tokens": "For advanced users. Manually provide the login token, user ID, and auth token."
        }
      },
      "tokens": {
        "data": {
          "auth_token": "Cloud API Auth Token"
        }
      },
      "select_devices": {
        "title": "Select Devices",
        "description": "Choose which IQAir devices to set up in Home Assistant.",
        "data": {
          "device_ids": "Devices"
        }
      },
      "reauth_confirm": {
        "title": "Re-authenticate",
        "description": "Your IQAir credentials have expired. Please re-authenticate.",
        "menu_options": {
          "reauth_credentials": "Email and Password",
          "reauth_tokens": "Manual Tokens"
        }
      },
      "reauth_credentials": {
        "title": "Re-authenticate with Email",
        "description": "Enter your IQAir email and password to refresh your credentials."
      },
      "reauth_tokens": {
        "title": "Re-authenticate with Tokens",
        "description": "Enter updated tokens to refresh your credentials."
      }
    },
    "abort": {
      "reauth_successful": "Re-authentication successful"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Device Selection",
        "description": "Select which IQAir devices to include in Home Assistant.",
        "data": {
          "device_ids": "Devices"
        }
      }
    }
  }
}
```

- [ ] **Step 2: Update manifest.json — bump version**

Change version from `"1.1.1"` to `"2.0.0"`:

```json
{
    "domain": "iqair_cloud",
    "name": "IQAir Cloud",
    "codeowners": ["@ThioJoe"],
    "documentation": "https://github.com/ThioJoe/HA-IQAir-Integration",
    "issue_tracker": "https://github.com/ThioJoe/HA-IQAir-Integration/issues",
    "config_flow": true,
    "iot_class": "cloud_polling",
    "version": "2.0.0",
    "requirements": [
        "httpx[http2]"
    ]
}
```

- [ ] **Step 3: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('custom_components/iqair_cloud/translations/en.json')); json.load(open('custom_components/iqair_cloud/manifest.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/iqair_cloud/translations/en.json custom_components/iqair_cloud/manifest.json
git commit -m "feat: update translations for multi-device flow, bump to v2.0.0"
```

---

## Chunk 5: Verification

### Task 13: Full syntax check and integration validation

**Files:**
- All files in `custom_components/iqair_cloud/`

- [ ] **Step 1: Verify all Python files parse correctly**

Run: `for f in custom_components/iqair_cloud/*.py; do python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f" || echo "FAIL: $f"; done`
Expected: All files print `OK`

- [ ] **Step 2: Verify all JSON files are valid**

Run: `for f in custom_components/iqair_cloud/*.json custom_components/iqair_cloud/translations/*.json; do python3 -c "import json; json.load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"; done`
Expected: All files print `OK`

- [ ] **Step 3: Verify imports resolve within the package**

Run: `python3 -c "
import ast, os
pkg = 'custom_components/iqair_cloud'
files = [f for f in os.listdir(pkg) if f.endswith('.py')]
for f in files:
    tree = ast.parse(open(os.path.join(pkg, f)).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('.'):
            mod = node.module.lstrip('.') + '.py'
            if mod != '.py' and not os.path.exists(os.path.join(pkg, mod)):
                print(f'MISSING: {f} imports {node.module} -> {mod}')
print('Import check done')
"`
Expected: `Import check done` with no MISSING lines

- [ ] **Step 4: Review the complete file list**

Run: `ls -la custom_components/iqair_cloud/`
Expected files:
- `__init__.py` (modified)
- `api.py` (modified)
- `binary_sensor.py` (new)
- `config_flow.py` (modified)
- `const.py` (modified)
- `coordinator.py` (modified)
- `entity.py` (new)
- `exceptions.py` (unchanged)
- `fan.py` (modified)
- `manifest.json` (modified)
- `select.py` (modified)
- `sensor.py` (new)
- `switch.py` (modified)
- `translations/en.json` (modified)

---

## Manual Testing Guide

After deploying to Home Assistant:

1. **Upgrade path (existing v1 install):**
   - Restart HA with the new code
   - Check logs for "Migrating IQAir config entry from version 1 to 2"
   - Verify existing fan/switch/select entities still work
   - Verify fan entity unique ID migrated (no duplicate fan entity)

2. **Fresh install:**
   - Add the integration, authenticate
   - Verify multi-select device picker shows all devices
   - Select multiple devices, verify entities created for each

3. **Sensor verification:**
   - Check that AQI, PM2.5, Particle Count sensors have values
   - Check filter health shows percentage for each filter
   - Check filter level shows "normal" or "low"
   - Check CADR, total air volume, fan runtime sensors
   - Check WiFi signal percentage
   - Check connection status binary sensor
   - Check outdoor sensors (only one set per location)

4. **Control verification:**
   - Turn fan on/off — verify state updates
   - Change fan speed — verify percentage updates
   - Toggle switches — verify state updates
   - Change select options — verify state updates

5. **Options flow:**
   - Open integration options
   - Verify device multi-select with current selection pre-checked
   - Add/remove a device, verify entities created/removed

6. **Re-auth:**
   - Simulate expired token (or manually trigger re-auth)
   - Verify re-auth flow presents auth options
   - Complete re-auth, verify integration reloads
