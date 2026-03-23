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

The coordinator switches from calling `async_get_device_state(device_id)` (single device) to `async_get_devices()` (all devices in one API call). The coordinator stores the full device list keyed by device ID.

### Data Structure

```python
coordinator.data = {
    "devices": {
        "ui2_67fc033d...": { ... full device dict ... },
        "ui2_66fc263c...": { ... full device dict ... },
    },
    "outdoor_locations": {
        "5bc99349b3f912fa4c104aaf": { ... outdoor dict from first device with this location ... }
    }
}
```

### Command Handling

Control entities (fan, switch, select) pass the target device's serial number when issuing gRPC commands. `update_from_command` merges the response into the correct device's data within the coordinator.

## Config Flow Changes

### Initial Setup

1. User authenticates (credentials or manual tokens — unchanged)
2. Flow fetches all devices via `async_get_devices()`
3. Multi-select form presents all devices by name; user checks which to set up (minimum 1)
4. Config entry stores `CONF_DEVICE_IDS` (list of selected device IDs)

### Options Flow

Adds a device selection step:
1. Re-fetches device list from API
2. Shows multi-select pre-checked with currently selected devices
3. On save, entities for removed devices are cleaned up; entities for new devices are created

### Config Migration

On load, if `CONF_DEVICE_ID` (old single-device format) exists and `CONF_DEVICE_IDS` does not, automatically migrate to `CONF_DEVICE_IDS = [CONF_DEVICE_ID]` and increment the config entry version.

Serial numbers, API endpoint, and device prefix are no longer stored in config — they are derived from the API response data and device `model` field.

## Device Registry & Entity Structure

### HA Device Entries

Each IQAir device gets its own HA device registry entry:
- **Identifiers:** `(DOMAIN, serialNumber)`
- **Name:** device `name` from API
- **Model:** `modelLabel`
- **Manufacturer:** "IQAir"
- **SW Version:** `modelVariation`

### Entity Unique IDs

Format: `{serial_number}_{entity_type}`

Examples:
- `UI2_050R-F06F-E110-1_aqi`
- `UI2_050R-F06F-E110-1_filter_1_health`
- `5bc99349b3f912fa4c104aaf_outdoor_aqi`

### Base Entity

`IQAirEntity(CoordinatorEntity)` in a new `entity.py`:
- Holds `device_id`
- Provides `device_data` property returning `coordinator.data["devices"][device_id]`
- Provides `device_info` property for HA device registry
- All platform entities (fan, switch, select, sensor) inherit from this

### Outdoor Entities

Created per unique outdoor location ID (`current.outdoor.id`):
- Associated with a synthetic HA device entry named by city (e.g., "Druid Hills Outdoor Air Quality")
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
| Fan Speed | `current.fanSpeed` | — | — | `measurement` |

### Filter Sensors (per device, per filter — dynamic count)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| Filter Health | `filters[n].healthPercent` | % | — | `measurement` |
| Filter Level | `filters[n].filterLevel` | — | `enum` | — |

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

### Connectivity Sensors (per device)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| WiFi Signal | `connectivity.percentage` | % | — | `measurement` |
| Connection Status | `isConnected` | — | `connectivity` | — |

### Outdoor Sensors (per unique location)

| Sensor | Source Path | Unit | Device Class | State Class |
|--------|-----------|------|-------------|-------------|
| Outdoor AQI | `outdoor.aqi` | — | `aqi` | `measurement` |
| Outdoor PM2.5 | `outdoor.pm25` | µg/m³ | `pm25` | `measurement` |
| Outdoor Temperature | `outdoor.temperature` | °F | `temperature` | `measurement` |
| Outdoor Humidity | `outdoor.humidity` | % | `humidity` | `measurement` |
| Outdoor Pressure | `outdoor.pressure` | Hg | `pressure` | `measurement` |
| Wind Speed | `outdoor.wind.speed` | — | `wind_speed` | `measurement` |
| Wind Direction | `outdoor.wind.direction` | ° | — | `measurement` |
| Weather Condition | `outdoor.condition` | — | `enum` | — |

## File Changes

### Modified Files

- **`const.py`** — add `CONF_DEVICE_IDS`, sensor key constants, `Platform.SENSOR`
- **`coordinator.py`** — multi-device data storage keyed by device ID; outdoor dedup tracking
- **`config_flow.py`** — multi-select device step in setup and options flows; config migration
- **`__init__.py`** — add `SENSOR` platform, multi-device setup, pass device list to platforms
- **`fan.py`** — refactor to create one fan per selected device, inherit from base entity
- **`switch.py`** — same refactoring
- **`select.py`** — same refactoring
- **`manifest.json`** — bump version

### New Files

- **`entity.py`** — `IQAirEntity(CoordinatorEntity)` base class with device ID lookup, coordinator data access, device info
- **`sensor.py`** — all sensor entity definitions using `SensorEntityDescription` dataclasses; factory function creates entities per device including dynamic filter sensors

## Error Handling & Edge Cases

**Device goes offline:** `isConnected` sensor reflects this. Other sensors keep last known value (standard HA polling behavior).

**Missing data fields:** Sensors return `None` (unknown state) when their data path is missing. Use `.get()` chains for safe access.

**Filter count changes:** Filter sensors are created at platform setup based on initial data. If filter configuration changes, user reloads the integration.

**Device added/removed from account:** Handled via Options flow — user re-selects devices. Not auto-detected during polling.

**Outdoor location deduplication:** Tracked by `current.outdoor.id`. If devices move to different locations, user reloads to pick up changes.

**Config migration:** On load, `CONF_DEVICE_ID` (old) is migrated to `CONF_DEVICE_IDS = [CONF_DEVICE_ID]` with config version increment.
