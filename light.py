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

DOMAIN = "neewerlight"

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger("NeewerLightEntity")
LOGGER.setLevel(logging.DEBUG)

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
		self._isTransitioning = False
		self._fade_time = 0.0

	@property
	def available(self):
		return self._instance.is_on != None

	@property
	def brightness(self):
		if self._instance.white_brightness:
			return self._instance.white_brightness

		if self._instance.rgb_color:
			return max(self._instance.rgb_color)

		LOGGER.info("Instance has no brightness attributes?")
		return None

	@property
	def is_on(self) -> Optional[bool]:
		return self._instance.is_on

	@property
	# RGB color/brightness based on https://github.com/home-assistant/core/issues/51175
	def rgb_color(self):
		if self._instance.rgb_color:
			return match_max_scale((255,), self._instance.rgb_color)
		return None

	@property
	def color_mode(self):
		if self._instance.rgb_color:
			if self._instance.rgb_color == (255, 255, 255):
				return COLOR_MODE_WHITE
			return COLOR_MODE_RGB
		return None

	@property
	def supported_features(self):
		return self._attr_supported_features

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
		if self._isTransitioning:
			self._isTransitioning = False
			LOGGER.info("Canceled transition due to new update")

		if not self.is_on:
			await self._instance.turn_on()

		transition = kwargs.get(ATTR_TRANSITION,self._fade_time)

		if ATTR_WHITE in kwargs:
			if kwargs[ATTR_WHITE] != self.brightness:
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

	async def _async_turn_on(self, brightness, color, transition=0.0):
		''' helper for controling whether to call doTransition or just set the color immediately '''
		if transition==0.0:
			await self._instance.set_color(color,brightness)
		else:
			asyncio.ensure_future(self.async_doTransition(brightness,color,transition))

	async def async_doTransition(self, endBrightness, endColor, transition, msPerFrame=20):
		self._isTransitioning = True
		LOGGER.info("Starting transition to "+str(endBrightness)+" "+str(endColor)+" with time "+str(transition)+", msPerFrame: "+str(msPerFrame))

		numFrames = max(int(transition/msPerFrame),1)
		originalBrightness = self.brightness
		originalColor = self.rgb_color
		if originalColor is None:
			originalColor = [0,0,0]
		if originalBrightness is None:
			originalBrightness = 0

		for i in range(1,numFrames+1):
			if not self._isTransitioning:
				break
			newColor = [
				int(originalColor[0] + i * (endColor[0] - originalColor[0])),
				int(originalColor[1] + i * (endColor[1] - originalColor[1])),
				int(originalColor[2] + i * (endColor[2] - originalColor[2]))
			]
			newBrightness = int(originalBrightness + i*(endBrightness-originalBrightness))

			timeStart = time.time()
			await self._instance.set_color(newColor,newBrightness)
			timeTaken = time.time() - timeStart
			if timeTaken*1000 < msPerFrame:
				await asyncio.sleep(msPerFrame-timeTaken)
			else:
				LOGGER.debug("msPerFrame exceeded due to long set_color, running as fast as possible")

		self._isTransitioning = False



	async def async_turn_off(self, **kwargs: Any) -> None:
		await self._instance.turn_off()

	async def async_update(self) -> None:
		await self._instance.update()
