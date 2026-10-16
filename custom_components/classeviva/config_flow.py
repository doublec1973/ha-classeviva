"""Config flow ClasseViva."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .schooldays import parse_closures
from .api import (
    ClasseVivaAuthError,
    ClasseVivaBlockedError,
    ClasseVivaClient,
    ClasseVivaError,
)
from .const import (
    CONF_CLOSURES,
    CONF_KEYWORDS,
    CONF_SATURDAY,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEYWORDS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
)


class ClasseVivaConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _try_login(self, username: str, password: str):
        client = ClasseVivaClient(async_get_clientsession(self.hass), username, password)
        errors: dict[str, str] = {}
        try:
            await client.login()
        except ClasseVivaAuthError:
            errors["base"] = "invalid_auth"
        except ClasseVivaBlockedError:
            errors["base"] = "blocked"
        except ClasseVivaError:
            errors["base"] = "cannot_connect"
        return client, errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client, errors = await self._try_login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if not errors:
                await self.async_set_unique_id(client.ident)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=client.full_name, data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            _, errors = await self._try_login(
                entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ClasseVivaOptionsFlow()


class ClasseVivaOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        opts = dict(self.config_entry.options)
        if user_input is not None:
            _, invalid = parse_closures(user_input.get(CONF_CLOSURES))
            if invalid:
                errors[CONF_CLOSURES] = "invalid_closures"
                opts = {**opts, **user_input}
            else:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=1440)),
                    vol.Required(
                        CONF_SATURDAY, default=opts.get(CONF_SATURDAY, False)
                    ): bool,
                    vol.Optional(
                        CONF_KEYWORDS,
                        description={
                            "suggested_value": opts.get(CONF_KEYWORDS, DEFAULT_KEYWORDS)
                        },
                    ): str,
                    vol.Optional(
                        CONF_CLOSURES,
                        description={"suggested_value": opts.get(CONF_CLOSURES, "")},
                    ): str,
                }
            ),
        )
