# PyModMonLCD
Python Modbus Monitor on Raspberry Pi with LCD output for solar systems 

The script provides a GUI wich will allow you to set up a ini-file for the channels to monitor (e.g. on a PC)
The script can then run on a Raspberry Pi without a monitor and will display the data on a LCD with 20x4 characters.

The data layout is fixed at the time of this writing.
Feel free to change it to your liking.

Inspired by: http://www.raspberrypi-spy.co.uk/2012/08/20x4-lcd-module-control-using-python/

pymodmon_glcd_led.py adds support for using a UC1701 based 64x128 pixel graphic LCD as well as to 14 LEDs via SPI shift registers(see [Schematic](./RasPi_LED_Extender.pdf)).

![GLCD Screenshot](./pymodmon_glcd.png?raw=true "GLCD Screenshot")
