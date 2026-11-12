"""Central fast poller for Rademacher wall controllers (push buttons)."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from homepilot.manager import HomePilotManager
from homepilot.wallcontroller import HomePilotWallController

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    BUTTON_POLL_MAX_BACKOFF,
    BUTTON_POLL_TIMEOUT,
    DOMAIN,
    EVENT_BUTTON_PRESSED,
)

_LOGGER = logging.getLogger(__name__)


class WallControllerPoller:
    """Polls all wall controllers of one config entry in a single loop.

    On every detected key press a `rademacher_button_pressed` event is fired
    and the registered channel entities are updated immediately.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        manager: HomePilotManager,
        exclude_devices: list[str],
        interval: float,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._interval = interval
        self._devices: list[HomePilotWallController] = [
            device
            for did, device in manager.devices.items()
            if did not in exclude_devices
            and isinstance(device, HomePilotWallController)
            and device.channels
        ]
        self._listeners: dict[str, list[Callable[[], None]]] = {}
        self._task: asyncio.Task | None = None
        # did -> (consecutive failures, loop time of next attempt)
        self._failures: dict[str, tuple[int, float]] = {}

    @callback
    def async_start(self) -> None:
        """Start the polling loop."""
        if not self._devices or self._task is not None:
            return
        _LOGGER.info(
            "%s - Polling %s wall controller(s) every %s s",
            self._entry.title,
            len(self._devices),
            self._interval,
        )
        self._task = self._entry.async_create_background_task(
            self._hass, self._async_run(), "rademacher wall controller poller"
        )

    @callback
    def async_stop(self) -> None:
        """Stop the polling loop, cancelling a running poll."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @callback
    def async_add_listener(self, did: str, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a callback invoked when channels of `did` changed."""
        self._listeners.setdefault(did, []).append(update_callback)

        @callback
        def _remove() -> None:
            listeners = self._listeners.get(did, [])
            if update_callback in listeners:
                listeners.remove(update_callback)

        return _remove

    async def _async_run(self) -> None:
        """Poll, then sleep for the rest of the interval (polls never overlap)."""
        loop = self._hass.loop
        while True:
            started = loop.time()
            # return_exceptions: wait for all devices so polls never overlap.
            results = await asyncio.gather(
                *(
                    self._async_poll_device(device)
                    for device in self._devices
                    if self._failures.get(device.did, (0, 0.0))[1] <= started
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Unexpected error polling wall controllers", exc_info=result
                    )
            await asyncio.sleep(max(self._interval - (loop.time() - started), 0))

    async def _async_poll_device(self, device: HomePilotWallController) -> None:
        did = device.did
        before_ts = dict(device.channels)
        before = {ch: getattr(device, f"channel_{ch}", False) for ch in before_ts}
        try:
            async with asyncio.timeout(BUTTON_POLL_TIMEOUT):
                await device.update_channels()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pylint: disable=broad-except
            # Back off (1 s, 2 s, 4 s ... max BUTTON_POLL_MAX_BACKOFF) and log once.
            failures = self._failures.get(did, (0, 0.0))[0] + 1
            backoff = min(
                max(self._interval, 1.0) * 2 ** min(failures - 1, 10),
                BUTTON_POLL_MAX_BACKOFF,
            )
            self._failures[did] = (failures, self._hass.loop.time() + backoff)
            if failures == 1:
                _LOGGER.warning(
                    "Polling wall controller %s (%s) failed: %r", device.name, did, err
                )
            # Do not leave a channel "on" while the device is backing off.
            if any(before.values()):
                for channel in before:
                    setattr(device, f"channel_{channel}", False)
                self._async_notify(did)
            return
        if self._failures.pop(did, None) is not None:
            _LOGGER.info("Polling wall controller %s (%s) recovered", device.name, did)

        # A press is a timestamp that moved forward. A timestamp going backwards
        # (e.g. bridge restart) is only a resync and must not trigger automations.
        after = {}
        for channel, new_ts in device.channels.items():
            old_ts = before_ts.get(channel)
            pressed = new_ts is not None and new_ts != old_ts
            if pressed and old_ts is not None:
                try:
                    pressed = new_ts > old_ts
                except TypeError:
                    pass
            setattr(device, f"channel_{channel}", pressed)
            after[channel] = pressed
            if pressed:
                self._async_fire_event(device, channel)

        if after != before:
            self._async_notify(did)

    @callback
    def _async_notify(self, did: str) -> None:
        for update_callback in list(self._listeners.get(did, [])):
            try:
                update_callback()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error updating wall controller entity of %s", did)

    @callback
    def _async_fire_event(self, device: HomePilotWallController, channel: int) -> None:
        device_registry = dr.async_get(self._hass)
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, f"{self._entry.unique_id or 'unknown'}_{device.did}")}
        )
        data = {
            "device_id": device_entry.id if device_entry else None,
            "did": str(device.did),
            "channel": channel,
            "name": device.name,
            "entry_id": self._entry.entry_id,
        }
        _LOGGER.debug("Button pressed: %s", data)
        self._hass.bus.async_fire(EVENT_BUTTON_PRESSED, data)
