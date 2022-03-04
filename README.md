# NeewerLitePython
A Python library for controlling Neewer RGB panels from python, specifically for use in Home Assistant

To work on windows, the winrt/client.py file from the bleak library needs to be edited otherwise the connection will always timeout. Comment the following line:

`#await asyncio.wait_for(event.wait(), timeout=timeout) `
