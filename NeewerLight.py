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
        self.isPoweredOn = False

    async def init(self):
        try:
            await self.device.connect(timeout=10.0)
            print("Services: "+str([v.uuid for k,v in self.device.services.services.items()]))
            print("Characteristics: "+str([v.uuid for k,v in self.device.services.characteristics.items()]))
        finally:
            await self.device.disconnect()
            
    def _write(self, characteristic, data):
        LOGGER.debug("Writing: "+(''.join(format(x, ' 03x') for x in data))+" to "+characteristic)
        #try:
        if not self.device.is_connected:
            await self.device.connect()
        await self.device.write_gatt_char(characteristic, data)
        #except Exception:
            

    def composeCommand(self, tag, vals):
        length = len(vals)
        command = [NEEWER_COMMAND_PREFIX]
        command.append(tag)
        command.append(length)
        command.extend(vals)
        return bytearray(NeewerLight.appendChecksum(command))

    async def set_color(self, rgb: Tuple[int,int,int]):
        r, g, b = rgb
        h,s,v = colorsys.rgb_to_hsv(r/255.0,g/255.0,b/255.0)
        h = int(h*360)
        s = int(s*100)
        v = int(v*100)
        #TODO convert to Hue/Sat
        cmd = self.composeCommand(NEEWER_COMMAND_RGB, [h&0xFF,(h>>8)&0xFF,s&0xff,v&0xff])
        self.device.write_gatt_char(NEEWER_CONTROL_UUID, cmd)

    async def powerOn(self):
        LOGGER.debug("Sending power on")
        if not self.device.is_connected:
            await self.device.connect()
        await self.device.write_gatt_char(self.controlGATT, bytearray([0x69,0x69,0x69]))
        await self.device.write_gatt_char(self.controlGATT, bytearray([0x69, 0x69, 0x69]))
        await self.device.write_gatt_char(self.readGATT, bytearray([0x69, 0x69, 0x69]))
        self.isPoweredOn = True

    async def powerOff(self):
        LOGGER.debug("Sending power off")
        await self.device.write_gatt_char(self.controlGATT, NEEWER_POWER_OFF)
        self.isPoweredOn = False

    async def sendReadRequest(self):
        LOGGER.debug("Sending read request")
        await self.device.write_gatt_char(self.controlGATT, NEEWER_READ_REQUEST)

    async def readStatus(self, callback):
        if not self.device.is_connected:
            await self.device.connect()
            # check characteristics

        future = asyncio.get_event_loop().create_future()
        await self._device.start_notify(self.readGATT, create_status_callback(future))
        await self.device.write_gatt_char(self.controlGATT, NEEWER_READ_REQUEST)

        await asyncio.wait_for(future, 5.0)
        await self._device.stop_notify(self.readGATT)

        res = future.result()
        if res[0]==NEEWER_UPDATE_PREFIX[0] and res[1]==NEEWER_UPDATE_PREFIX[1] and res[2]==NEEWER_UPDATE_PREFIX[2]:
            LOGGER.info("Update prefix")
        LOGGER.info("Read data: %s",str(res))
        hexPrint(res)


        # self.device.start_notify(self.readGATT, )

    @classmethod
    async def discover(cls):
        """Disover BLE devices, specifically the Neewer lights"""
        LOGGER.debug("Discovering devices...")
        devices = await BleakScanner.discover()
        LOGGER.debug("Discovered devices: %s", [{"address": device.address, "name": device.name} for device in devices])
        return [device for device in devices if
                device.name is not None and device.name.lower().startswith("laurie")]

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


async def main():
    devices = await NeewerLight.discover()
    if len(devices):
        d = NeewerLight(devices[0])
        await d.init()
        # input("Pause")
        await d.powerOn()
        print("done")

asyncio.run(main())
