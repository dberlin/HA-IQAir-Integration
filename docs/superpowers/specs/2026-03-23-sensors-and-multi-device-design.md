# IQAir Integration: Sensors & Multi-Device Support

## Overview

Add sensor entities to the IQAir Cloud Home Assistant integration to expose air quality, filter health, performance, connectivity, and outdoor weather data. Simultaneously refactor the integration from single-device to multi-device support with user-selectable devices.

## Goals

1. Expose all available API data as HA sensor entities (indoor AQI, PM2.5, particle count, filter health, performance stats, connectivity, outdoor weather)
2. Support multiple devices per config entry with user selection during setup
3. Deduplicate outdoor weather sensors across devices sharing the same location
4. Maintain backward compatibility with existing single-device config entries

## Data Architecture & Coordinator

### Polling Change

The coordinator switches from calling `async_get_device_state(device_id)` (single device) to `async_get_devices()` (all devices in one API call). The coordinator stores the full device list keyed by device ID, filtered to only the user-selected devices.

### Data Structure

```python
coordinator.data = {
    "devices": {
        "ui2_67fc033d...": { ... full device dict ... },
        "ui2_66fc263c...": { ... full device dict ... },
    },
    "outdoor_locations": {
        "5bc99349b3f912fa4c104aaf": { ... outdoor dict ... }
    }
}
```

Outdoor location tracking: on each poll, the coordinator iterates selected devices and populates `outdoor_locations` keyed by location ID. If multiple devices share a location, the first one encountered provides the data — the iteration order is deterministic (sorted by device ID) so the source is stable. No cross-reload persistence is needed because the outdoor data is identical for all devices at the same location (it comes from the same city-level source). Source stability is a convenience, not a correctness requirement.

### Command Handling

Control entities (fan, switch, select) pass the target device's serial number when issuing gRPC commands.

`update_from_command` signature changes to `update_from_command(device_id, update_data)`. It merges the response into `coordinator.data["devices"][device_id]["remote"]`.

### API Client Refactoring

The `IQAirApiClient` command methods (`set_power`, `set_fan_speed`, etc.) must accept `serial_number` and `device_prefix` as parameters rather than reading them from instance state. `_build_payload` likewise accepts serial number as a parameter.

Model-to-prefix mapping:
- `model == "ui2"` → prefix `"UI2"`, endpoint `grpc.ui2.v1.UI2Service`
- `model == "klr"` → prefix `"KLR"`, endpoint `grpc.klr.v1.KLRService`

These are derived at command time from the device's data in the coordinator.

## Config Flow Changes

### Initial Setup

1. User authenticates (credentials or manual tokens — unchanged)
2. Flow fetches all devices via `async_get_devices()`
3. Multi-select form presents all devices by name; user checks which to set up (minimum 1)
4. Config entry stores `CONF_DEVICE_IDS` (list of selected device IDs)

### Config Entry Unique ID

The config entry unique ID changes from `device_id` to `user_id`. This ensures one config entry per IQAir account regardless of which devices are selected. `_abort_if_unique_id_configured()` prevents duplicate entries for the same account.

### Options Flow

Replaces the existing endpoint/prefix options flow with a device selection step:
1. Re-fetches device list from API
2. Shows multi-select pre-checked with currently selected devices
3. On save, entities for removed devices are cleaned up; entities for new devices are created

The old API endpoint and device prefix options are removed — these are now derived from each device's `model` field.

### Re-auth Flow

Re-auth step sequence: `async_step_reauth` → `async_step_reauth_confirm` (new step). This is a dedicated step that presents the credentials or tokens form (same as initial auth), validates them, then updates the config entry and reloads. It does NOT route through `async_step_user` or the device selection step.

Keys written on re-auth success: `CONF_AUTH_TOKEN`, `CONF_LOGIN_TOKEN`, and `CONF_USER_ID` (all three are refreshed from the sign-in response, even if the user re-authenticates with the same account). The update call: `hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, CONF_AUTH_TOKEN: new_auth_token, CONF_LOGIN_TOKEN: new_login_token, CONF_USER_ID: new_user_id})` followed by `hass.config_entries.async_reload(config_entry.entry_id)`.

### Config Migration

Implement `async_migrate_entry(hass, config_entry)` in `__init__.py`:
- If `config_entry.version == 1`: migrate `CONF_DEVICE_ID` → `CONF_DEVICE_IDS = [CONF_DEVICE_ID]`, remove `CONF_SERIAL_NUMBER`, `CONF_API_ENDPOINT`, `CONF_DEVICE_PREFIX` from config data. Call `hass.config_entries.async_update_entry(config_entry, version=2, data=new_data)`. Return `True`.
- If `config_entry.version >= 2`: return `True` (already migrated, nothing to do).
- For any unrecognized version: return `False`.
- Set `ConfigFlow.VERSION = 2`.
- `CONF_DEVICE_ID` remains in `const.py` as a deprecated constant — it is needed by the migration code to read the old value. Add a comment marking it as deprecated.

### Translation Updates

Add translation keys in `translations/en.json` for:
- `select_devices` step title and description
- `device_ids` data field label
- Options flow device selection step

## Device Registry & Entity Structure

### HA Device Entries

Each IQAir device gets its own HA device registry entry:
- **Identifiers:** `(DOMAIN, device_id)` — uses the API `id` field (e.g., `ui2_67fc033d...`), consistent with the existing code to avoid orphaning existing device entries on upgrade
- **Name:** device `name` from API
- **Model:** `modelLabel`
- **Manufacturer:** "IQAir"
- **SW Version:** `modelVariation`

### Entity Unique IDs

Format: `{device_id}_{entity_type}`

Uses `device_id` (not serial number) to maintain continuity with existing entities. The current fan entity uses bare `device_id` as its unique ID — this is migrated to `{device_id}_fan` for consistency with the new scheme.

Examples:
- `ui2_67fc033d..._aqi`
- `ui2_67fc033d..._filter_1_health`
- `ui2_67fc033d..._fan` (was previously just `ui2_67fc033d...`)

Outdoor entities use location ID:
- `5bc99349b3f912fa4c104aaf_outdoor_aqi`

### Existing Entity Migration

The fan entity unique ID changes from `{device_id}` to `{device_id}_fan`. Implement entity migration in the fan platform's `async_setup_entry` to update the entity registry entry's unique_id, avoiding orphaned entities.

Switch unique IDs already use `{device_id}_{description_key}` format (e.g., `{device_id}_auto_mode`). Select unique IDs already use `{device_id}_auto_mode_profile` / `{device_id}_light_level`. Both match the new `{device_id}_{entity_type}` scheme — no migration needed.

### Base Entity

`IQAirEntity(CoordinatorEntity)` in a new `entity.py`:
- Holds `device_id`
- Provides `device_data` property returning `coordinator.data["devices"][device_id]`
- Provides `device_info` property for HA device registry using `(DOMAIN, device_id)` as identifier
- All platform entities (fan, switch, select, sensor, binary_sensor) inherit from this

### Outdoor Entities

Created per unique outdoor location ID (`current.outdoor.id`):
- Associated with a synthetic HA device entry:
  - **Identifiers:** `(DOMAIN, "outdoor_{location_id}")`
  - **Name:** "{city} Outdoor Air Quality" (e.g., "Druid Hills Outdoor Air Quality")
  - **Manufacturer:** "IQAir"
- Unique IDs use location ID: `{location_id}_outdoor_{sensor_type}`
- If multiple devices share the same outdoor location, only one set of outdoor sensors is created

## Sensor Entities

### Indoor Air Quality (per device)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| AQI | `current.aqi.value` | — | `aqi` | `measurement` |
| AQI Label | `current.aqi.label` | — | `enum` | — |
| PM2.5 | `current.pm25.value` | µg/m³ | `pm25` | `measurement` |
| Particle Count | `current.pc.value` | — | — | `measurement` |

AQI Label enum options: `["Good", "Moderate", "Unhealthy for Sensitive Groups", "Unhealthy", "Very Unhealthy", "Hazardous"]` (standard US AQI categories).

Note: `current.fanSpeed` is NOT exposed as a separate sensor — the fan control entity already exposes speed via its percentage/preset attributes, making a separate sensor redundant.

### Filter Sensors (per device, per filter — dynamic count)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| Filter Health | `filters[n].healthPercent` | % | — | `measurement` |
| Filter Level | `filters[n].filterLevel` | — | `enum` | — |

Filter Level enum options: `["normal", "low"]` (values observed from API).

Named using filter medium name when available, slot number as fallback:
- "Main Particle Filter Health"
- "Gas and Odour Filter Health"
- Fallback: "Filter 1 Health", "Filter 2 Health"

### Performance Sensors (per device)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| CADR % | `performance.cleanAirDeliveryRatePercent` | % | — | `measurement` |
| Total Air Volume | `performance.totCumAirVolume` | m³ | `volume` | `total_increasing` |
| Total Fan Runtime | `performance.totTimeFanRun` | — | — | — |

Note: `totTimeFanRun` is a human-readable string from the API (e.g., "10 months", "a year"), not a numeric duration. Exposed as a plain text sensor with no device class or unit.

### Connectivity Sensors (per device)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| WiFi Signal | `connectivity.percentage` | % | — | `measurement` |

### Connection Status Binary Sensor (per device)

`isConnected` is exposed as a `BinarySensorEntity` on the `binary_sensor` platform, not a regular sensor:
- **Device class:** `BinarySensorDeviceClass.CONNECTIVITY`
- **`is_on`:** `True` when `isConnected` is `True`

This requires adding `Platform.BINARY_SENSOR` to the platforms list.

### Outdoor Sensors (per unique location)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| Outdoor AQI | `outdoor.aqi` | — | `aqi` | `measurement` |
| Outdoor PM2.5 | `outdoor.pm25` | µg/m³ | `pm25` | `measurement` |
| Outdoor Temperature | `outdoor.temperature` | °F | `temperature` | `measurement` |
| Outdoor Humidity | `outdoor.humidity` | % | `humidity` | `measurement` |
| Outdoor Pressure | `outdoor.pressure` | inHg | `pressure` | `measurement` |
| Wind Speed | `outdoor.wind.speed` | mph | `wind_speed` | `measurement` |
| Wind Direction | `outdoor.wind.direction` | ° | — | `measurement` |
| Weather Condition | `outdoor.condition` | — | `enum` | — |

Weather Condition enum options: `["Clear sky", "Few clouds", "Scattered clouds", "Broken clouds", "Shower rain", "Rain", "Thunderstorm", "Snow", "Mist"]` (standard weather icon mappings).

Note: The API uses imperial units (`"units.system": "imperial"` in request params). All unit values must use HA's typed unit enums (`UnitOfTemperature.FAHRENHEIT`, `UnitOfPressure.INHG`, `UnitOfSpeed.MILES_PER_HOUR`) as `native_unit_of_measurement`, not raw strings. HA will handle unit conversion for display based on user preferences. The `WEB_API_PARAMS` constant must remain imperial for these units to be correct.

## File Changes

### Modified Files

- **`const.py`** — add `CONF_DEVICE_IDS`, sensor key constants, `Platform.SENSOR`, `Platform.BINARY_SENSOR`, model-to-prefix/endpoint mapping
- **`coordinator.py`** — multi-device data storage keyed by device ID; outdoor dedup tracking with stable source selection; `update_from_command(device_id, update_data)` signature
- **`config_flow.py`** — multi-select device step in setup and options flows; `VERSION = 2`; config entry unique ID uses `user_id`; re-auth flow updated; old endpoint/prefix options removed; `validate_connection` updated to match new `IQAirApiClient` constructor signature
- **`__init__.py`** — add `SENSOR` and `BINARY_SENSOR` platforms; `async_migrate_entry` for v1→v2 config migration; multi-device setup; API client refactored for per-command serial numbers
- **`api.py`** — command methods accept `serial_number` and `device_prefix` parameters; `_build_payload` accepts serial number parameter; remove instance-level `_serial_number`; constructor signature changes (removes `serial_number`, `endpoint`, `device_prefix` params)
- **`fan.py`** — refactor to create one fan per selected device; inherit from base entity; entity unique ID migration from `{device_id}` to `{device_id}_fan`
- **`switch.py`** — same refactoring, inherit from base entity
- **`select.py`** — same refactoring, inherit from base entity
- **`manifest.json`** — bump version
- **`translations/en.json`** — add translation keys for device selection step and data fields

### New Files

- **`entity.py`** — `IQAirEntity(CoordinatorEntity)` base class with device ID lookup, coordinator data access, device info
- **`sensor.py`** — all sensor entity definitions using `SensorEntityDescription` dataclasses; factory function creates entities per device including dynamic filter sensors; outdoor sensor entities
- **`binary_sensor.py`** — connection status binary sensor entity

## Error Handling & Edge Cases

**Device goes offline:** `isConnected` binary sensor reflects this. Other sensors keep last known value (standard HA polling behavior).

**Missing data fields:** Sensors return `None` (unknown state) when their data path is missing. Use `.get()` chains for safe access.

**Filter count changes:** Filter sensors are created at platform setup based on initial data. If filter configuration changes, user reloads the integration.

**Device added/removed from account:** Handled via Options flow — user re-selects devices. Not auto-detected during polling.

**Outdoor location deduplication:** Tracked by `current.outdoor.id` with stable source device selection on the coordinator instance. If devices move to different locations, user reloads to pick up changes.

**Config migration:** `async_migrate_entry` in `__init__.py` handles v1→v2 migration. `ConfigFlow.VERSION` set to 2. Migration converts `CONF_DEVICE_ID` to `CONF_DEVICE_IDS` list and removes deprecated config keys.

**Entity unique ID migration:** Fan entity unique ID migrated from `{device_id}` to `{device_id}_fan` via entity registry update in platform setup.

**Re-auth flow:** Updated to work without `CONF_DEVICE_ID`/`CONF_SERIAL_NUMBER`. Only refreshes tokens, no device selection.
