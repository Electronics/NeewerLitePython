import traceback
from typing import Tuple
from bleak import BleakClient, BleakScanner
import colorsys
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger("NeewerLight")
LOGGER.setLevel(logging.DEBUG)

NEEWER_SERVICE_UUID = "69400001-b5a3-f393-e0a9-e50e24dcca99"
NEEWER_CONTROL_UUID = "69400002-b5a3-f393-e0a9-e50e24dcca99"
NEEWER_READ_UUID = "69400003-b5a3-f393-e0a9-e50e24dcca99"
# these commands are in the format 0x78 (prefix), <something>, length of data following, data, checksum
NEEWER_POWER_ON = bytearray([0x78,0x81,0x01,0x01,0xFB])
NEEWER_POWER_OFF = bytearray([0x78,0x81,0x01,0x02,0xFC])
NEEWER_READ_REQUEST = bytearray([0x78,0x84,0x00,0xFC])
NEEWER_UPDATE_PREFIX = bytearray([0x78,0x01,0x01])
NEEWER_COMMAND_PREFIX = 0x78
NEEWER_COMMAND_RGB = 0x86
NEEWER_COMMAND_CCT = 0x87
NEEWER_COMMAND_SCENE = 0x88
NEEWER_COMMAND_BRIGHTNESS = 0x82
NEEWER_COMMAND_COLOURTEMP = 0x83

def hexPrint(l):
    print('['+(', '.join(hex(x) for x in l))+"]")

def create_status_callback(future: asyncio.Future):
    def callback(sender: int, data: bytearray):
        if not future.done():
            future.set_result(data)
    return callback

class NeewerLight:

    def __init__(self, device, controlCharacteristic = NEEWER_CONTROL_UUID, readCharacteristic = NEEWER_READ_UUID):
        LOGGER.debug("New device: %s",str(device))
        self.device = BleakClient(device, use_cached=False)
        self.controlGATT = controlCharacteristic
        self.readGATT = readCharacteristic
        self._isPoweredOn = False
        self._mac = device
        self._rgbColor = (0,0,0)
        self._brightness = 0

    @property
    def mac(self):
        return self._mac

    @property
    def is_on(self):
        return self._isPoweredOn

    @property
    def rgb_color(self):
        return self._rgbColor

    @property
    def brightness(self):
        return self._brightness

    async def _write(self, characteristic, data):
        LOGGER.debug("Writing: "+(''.join(format(x, ' 03x') for x in data))+" to "+characteristic)
        #try:
        if not self.device.is_connected:
            await self.device.connect(timeout=5.0)
        await self.device.write_gatt_char(characteristic, data)
        #except Exception:


    def composeCommand(self, tag, vals):
        length = len(vals)
        command = [NEEWER_COMMAND_PREFIX]
        command.append(tag)
        command.append(length)
        command.extend(vals)
        return bytearray(NeewerLight.appendChecksum(command))

    async def set_color(self, rgb: Tuple[int,int,int], brightness = None):
        LOGGER.info("Set colour: "+str(rgb)+","+str(brightness))
        # rgb 0-255, brightness 0-255
        r, g, b = rgb
        self._rgbColor = (r,g,b) # TODO temporary as we don't read the color back from the light at the moment
        h,s,v = colorsys.rgb_to_hsv(r/255.0,g/255.0,b/255.0)
        h = int(h*360)
        s = int(s*100)
        v = int(self._brightness*100/256) # don't use v from colour, keep the same brightness
        LOGGER.info("turned into HSV: "+str(h)+" "+str(s)+" "+str(v))
        if brightness is not None:
            v = int(brightness*100/256)
            LOGGER.info("Brightness overwrite: "+str(v))
            self._brightness = brightness # TODO temporary as we don't read the color back from the light at the moment
        cmd = self.composeCommand(NEEWER_COMMAND_RGB, [h&0xFF,(h>>8)&0xFF,s&0xff,v&0xff])
        await self._write(NEEWER_CONTROL_UUID, cmd)

    async def set_white(self, intensity: int):
        # brightness 0-100
        await self.set_color((255,255,255),intensity)

    async def turn_on(self):
        await self.powerOn()

    async def turn_off(self):
        await self.powerOff()

    async def update(self):
        try:
            await self.readStatus()
        except (Exception) as error:
            LOGGER.error("Error getting status: %s",error)
            track = traceback.format_exc()
            LOGGER.debug(track)

    async def disconnect(self):
        if self.device.is_connected:
            await self.device.disconnect()

    async def powerOn(self):
        LOGGER.debug("Sending power on")
        await self._write(self.controlGATT, NEEWER_POWER_ON)
        self._isPoweredOn = True

    async def powerOff(self):
        LOGGER.debug("Sending power off")
        await self._write(self.controlGATT, NEEWER_POWER_OFF)
        self._isPoweredOn = False

    async def sendReadRequest(self):
        LOGGER.debug("Sending read request")
        await self._write(self.controlGATT, NEEWER_READ_REQUEST)

    async def setScene(self, scene, brightness=100):
        # scene 1-9, brightness 0-100
        # 1: police sirens, 2: police siren but stuck?, 3: ambulance?, 4: party mode A, 5: party mode B (A but faster), 6: party mode C (candlelight), 7-9: lightning
        await self._write(self.controlGATT, self.composeCommand(NEEWER_COMMAND_SCENE, [brightness&0xff,scene&0x0f]))

    async def readStatus(self):
        if not self.device.is_connected:
            await self.device.connect(timeout=10.0)
            # check characteristics

        future = asyncio.get_event_loop().create_future()
        await self.device.start_notify(self.readGATT, create_status_callback(future))
        await self.device.write_gatt_char(self.controlGATT, NEEWER_READ_REQUEST)

        await asyncio.wait_for(future, 10.0)
        await self.device.stop_notify(self.readGATT)

        res = future.result()
        if res[0]==NEEWER_UPDATE_PREFIX[0] and res[1]==NEEWER_UPDATE_PREFIX[1] and res[2]==NEEWER_UPDATE_PREFIX[2]:
            LOGGER.info("Update prefix")
        LOGGER.info("Read data: %s",str(res))
        hexPrint(res)
        #TODO: validate checksum?
        #TODO: don't actually know what RGB values return, it's not in the swift implementation


        # self.device.start_notify(self.readGATT, )

    @classmethod
    async def discover(cls):
        """Disover BLE devices, specifically the Neewer lights"""
        LOGGER.debug("Discovering devices...")
        devices = await BleakScanner.discover()
        LOGGER.debug("Discovered devices: %s", [{"address": device.address, "name": device.name} for device in devices])
        return [device for device in devices if
                device.name is not None and (device.name.lower().startswith("neewer") or device.name.lower().startswith("laurie"))]

    @classmethod
    def appendChecksum(cls, data: list):
        checksum = 0
        for i in range(len(data)):
            checksum += data[i] & 0xFF # should be a uint8 effectively, this could go wrong if the numbers were negative
        data.append(checksum & 0xFF)
        return data

    @classmethod
    def validateChecksum(cls, data: list):
        length = len(data)
        if length<2:
            return False

        checksum = 0
        for i in range(length-1):
            checksum += data[i]
        if checksum == data[length-1]:
            return True
        return False


# async def main():
#     devices = await NeewerLight.discover()
#     if len(devices):
#         d = NeewerLight(devices[0])
#         # await d.init()
#         # input("Pause")
#         await d.set_color((255,127,0))
#         print("done")
#
# asyncio.run(main())
