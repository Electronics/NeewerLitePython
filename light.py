import asyncio
import logging
import time

import voluptuous as vol
from typing import Any, Optional, Tuple

from .NeewerLight import NeewerLight

from homeassistant.const import CONF_MAC
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (COLOR_MODE_RGB, PLATFORM_SCHEMA,
											LightEntity, ATTR_RGB_COLOR, ATTR_BRIGHTNESS, COLOR_MODE_WHITE, ATTR_WHITE, SUPPORT_TRANSITION, ATTR_TRANSITION)
from homeassistant.util.color import (match_max_scale)
from homeassistant.helpers import device_registry
from homeassistant.core import callback

DOMAIN = "neewerlight"

#logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger("NeewerLightEntity")
LOGGER.setLevel(logging.WARN)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
	vol.Required(CONF_MAC): cv.string
})


async def async_setup_entry(hass, config_entry, async_add_devices):
	instance = hass.data[DOMAIN][config_entry.entry_id]
	async_add_devices([NeewerLightEntity(instance, config_entry.data["name"], config_entry.entry_id)])


class NeewerLightEntity(LightEntity):
	def __init__(self, lightInstance: NeewerLight, name: str, entry_id: str) -> None:
		self._instance = lightInstance
		self._entry_id = entry_id
		self._attr_supported_color_modes = {COLOR_MODE_RGB, COLOR_MODE_WHITE}
		self._attr_supported_features = SUPPORT_TRANSITION
		self._color_mode = None
		self._attr_name = name
		self._attr_unique_id = self._instance.mac
		self._isTransitioning = asyncio.Event()
		self._stopTransition = asyncio.Event()
		self._hasExitedTransition = asyncio.Event()
		self._transitionQueueCounter = 0
		self._fade_time = 0.0

	@property
	def available(self):
		return self._instance.is_on != None

	@property
	def brightness(self):
		return self._instance.brightness

	@property
	def is_on(self) -> Optional[bool]:
		return self._instance.is_on

	@property
	def should_poll(self):
		return False

	@property
	def fade_time(self):
		return self._fade_time

	@fade_time.setter
	def fade_time(self, value):
		self._fade_time = value

	@callback
	def _schedule_immediate_update(self):
		self.async_schedule_update_ha_state(True)

	def update(self):
		"""Fetch update state."""
		# Nothing to return

	@property
	# RGB color/brightness based on https://github.com/home-assistant/core/issues/51175
	def rgb_color(self):
		if self._instance.rgb_color:
			return match_max_scale((255,), self._instance.rgb_color)
		return None

	@property
	def color_mode(self):
		return COLOR_MODE_RGB

	@property
	def supported_features(self):
		return self._attr_supported_features

	@property
	def should_poll(self):
		return False

	@property
	def device_info(self):
		return {
			"identifiers": {
				(DOMAIN, self._instance.mac)
			},
			"name": self.name,
			"connections": {(device_registry.CONNECTION_NETWORK_MAC, self._instance.mac)},
			"config_entry_id": self._entry_id
		}

	def _transform_color_brightness(self, color: Tuple[int, int, int], set_brightness: int):
		rgb = match_max_scale((255,), color)
		LOGGER.debug("Transform scaled: "+str(rgb))
		LOGGER.debug("Transforming with brightness: "+str(set_brightness))
		res = tuple(color * set_brightness // 255 for color in rgb)
		return res

	async def async_turn_on(self, **kwargs: Any) -> None:
		if not self.is_on:
			await self._instance.turn_on()

		transition = kwargs.get(ATTR_TRANSITION,self._fade_time)

		if ATTR_WHITE in kwargs:
			if kwargs[ATTR_WHITE] != self.brightness:
				LOGGER.info("White set")
				await self._async_turn_on(kwargs[ATTR_WHITE], (255,255,255), transition)

		elif ATTR_RGB_COLOR in kwargs:
			LOGGER.info("Colour change: "+str(kwargs[ATTR_RGB_COLOR]))
			if kwargs[ATTR_RGB_COLOR] != self.rgb_color:
				#color = kwargs[ATTR_RGB_COLOR]
				bright = self.brightness
				if ATTR_BRIGHTNESS in kwargs:
					bright = kwargs[ATTR_BRIGHTNESS]
					#color = self._transform_color_brightness(color, kwargs[ATTR_BRIGHTNESS])
				else:
					LOGGER.debug("Brightness not given, using: "+str(self.brightness)+" with transition "+str(transition))
					#color = self._transform_color_brightness(color, self.brightness)
				await self._async_turn_on(bright, kwargs[ATTR_RGB_COLOR], transition)

		elif ATTR_BRIGHTNESS in kwargs and kwargs[ATTR_BRIGHTNESS] != self.brightness and self.rgb_color != None:
			LOGGER.debug("Just changing brightness (of coloured rgb) with brightness: "+str(kwargs[ATTR_BRIGHTNESS])+" with transition "+str(transition))
			await self._async_turn_on(kwargs[ATTR_BRIGHTNESS], self.rgb_color, transition)

		self.async_schedule_update_ha_state()

	async def _async_turn_on(self, brightness, color, transition=0.0):
		''' helper for controling whether to call doTransition or just set the color immediately '''
		if transition==0.0:
			if self._isTransitioning.is_set():
				self._stopTransition.set()
				LOGGER.info("Canceling transition due to new set-colour")
			await self._instance.set_color(color,brightness)
		else:
			asyncio.ensure_future(self.async_doTransition(brightness,color,transition))

	async def async_doTransition(self, endBrightness, endColor, transition, msPerFrame=40):
		if self._isTransitioning.is_set():
			LOGGER.info("Awaiting transition finish due to new set-colour")
			self._stopTransition.set()
			self._transitionQueueCounter += 1
			ticket = self._transitionQueueCounter # handles multiple transitions getting called and blocked at the same point
			await self._hasExitedTransition.wait()
			self._hasExitedTransition.clear()
			if self._transitionQueueCounter != ticket:
				LOGGER.info("Transition canceled by another waiting transition")
				return # canceled by another newer transition
		self._isTransitioning.set()
		self._hasExitedTransition.clear() # if there was an already completed transition a while ago
		LOGGER.info("Starting transition to "+str(endBrightness)+" "+str(endColor)+" with time "+str(transition)+", msPerFrame: "+str(msPerFrame))

		numFrames = max(int(transition*1000/msPerFrame),1)
		originalBrightness = self.brightness
		originalColor = self.rgb_color
		if originalColor is None:
			originalColor = [0,0,0]
		if originalBrightness is None:
			originalBrightness = 0

		LOGGER.debug("Orig: "+str(originalColor)+" bright: "+str(originalBrightness))

		for i in range(1,numFrames+1):
			if self._stopTransition.is_set():
				break
			newColor = [
				int(originalColor[0] + i * (endColor[0] - originalColor[0]) / numFrames),
				int(originalColor[1] + i * (endColor[1] - originalColor[1]) / numFrames),
				int(originalColor[2] + i * (endColor[2] - originalColor[2]) / numFrames)
			]
			newBrightness = int(originalBrightness + i*(endBrightness-originalBrightness) / numFrames)

			LOGGER.debug("Loop: "+str(i)+"/"+str(numFrames)+" c "+str(newColor)+" b "+str(newBrightness))

			timeStart = time.time()
			if newColor != self.rgb_color or newBrightness != self.brightness:
				await self._instance.set_color(newColor,newBrightness)
			timeTaken = time.time() - timeStart
			LOGGER.debug("took "+str(timeTaken)+" seconds to execute set_color")
			if timeTaken*1000 < msPerFrame:
				waitTime = msPerFrame/1000-timeTaken
				LOGGER.debug("Waiting "+str(waitTime)+"ms")
				await asyncio.sleep(waitTime)
			else:
				LOGGER.debug("msPerFrame exceeded due to long set_color, running as fast as possible")
		LOGGER.info("Finished transition")

		self._stopTransition.clear()
		self._isTransitioning.clear()
		self._hasExitedTransition.set()



	async def async_turn_off(self, **kwargs: Any) -> None:
		await self._instance.turn_off()
		self.async_schedule_update_ha_state()

	async def async_update(self) -> None:
		await self._instance.update()
