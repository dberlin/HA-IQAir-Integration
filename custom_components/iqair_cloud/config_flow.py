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

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._user_input: dict[str, Any] = {}
        self._devices: list[dict[str, Any]] = []

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
