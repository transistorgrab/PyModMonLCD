# coding=UTF-8

## @package pymodmon_CGLCD_LED
# Python Modbus Monitor for color graphics LCD (CGLCD) and LED output
# a small program that uses the pymodbus package to retrieve and
# display modbus slave data.

# requires: Python >3.7, pymodbus, docopt, pillow, spidev, RPi.GPIO, Adafruit_ILI9341
#
# Date created: 2019-02-25
# Author: André S.

## help message to display by docopt (and parsed by docopt for command line arguments)
'''Python Modbus Monitor color GLCD display module.
This module will display data on a graphical LCD with 240x320 pixels
It also provides the control for 14 LEDs (7 green, 7 red).

Usage:
    pymodmon_glcd_led.py
    pymodmon_glcd_led.py [-h|--help]
    pymodmon_glcd_led.py [--version]
    pymodmon_glcd_led.py -i <file>|--inifile=<file> [-L <sec>|--loginterval=<sec>] [-S|--single] [--nogui] [-P|--printtoconsole] [-g|--graphical]

Options:
    no options given in a xterm will open the TK interface
    -h, --help            Show this screen
    --version             Show version
    -i, --inifile=<file>  Uses the given file as input for communication and
                          log file settings and channel configuration
    -g, --graphical       show data on GLCD in graphical style instead of text
    -S, --single          Do only one read cycle instead of continuous reading.
    -L, --loginterval=<sec>  Read data every xx seconds. [defaul value: 5]
    -P, --printtoconsole  displays the data on console additionally to the
                          LCD on Raspberry Pi
'''
from tkinter import messagebox

## use docopt for command line parsing and displaying help message
try:
    import docopt
    from docopt import docopt
except ImportError:
    try: ## for command line showerror does not work
        messagebox.showerror('Import Error','docopt package was not found on your system.\nPlease install it using the command:\
                                \n"pip install docopt"')
    except:
        print('Import errror. docopt package was not found on your system. Please install it using the command: "pip install docopt"')

if __name__ == '__main__':
    arguments = docopt(__doc__, version='PyModMonGLCD 1.0')

## use pymodbus for the Modbus communication
try:
    from pymodbus import *
except ImportError:
    try: ## for command line showerror does not work
        messagebox.showerror('Import Error','pymodbus package was not found on your system.\nPlease install it using the command:\
                                \n"pip install pymodbus"')
    except:
        print('Import errror. pymodbus package was not found on your system. Please install it using the command: "pip install pymodbus"')

## spidev for SPI communication
try:
    import spidev
except ImportError:
    try: ## for command line showerror does not work
        messagebox.showerror('Import Error','spidev package was not found on your system.\nPlease install it.')
    except:
        print('Import errror. spidev package was not found on your system. Please install it.')

#import Raspberry Pi GPIO library for direct GPIO access
try:
    import RPi.GPIO as GPIO
except:
    ## if we have a GUI display an error dialog
    try:
        messagebox.showerror('Import Error','RPi.GPIO not found. Either this is no Rasberry Pi or the library is missing.')
    except: ## if no GUI display error and exit
        print('RPi.GPIO not found. Either this is no Rasberry Pi or the library is missing.')
        running_on_RPi = False

#import Raspberry Pi GPIO library for direct GPIO access
# which mode to address GPIOs (BCM: GPIO number, BOARD: connector pin number)
GPIO.setmode(GPIO.BCM)

## enable execution of functions on program exit
import atexit

## enable timed execution of the data polling
from threading import Timer

## enable file access
import os

## enable timeout use
import time

########################## LED class ###############################################################
## class for LED output related things
# LED config:
# 7 red, 1 backlight, 7 green
# red LEDs are on one device (first byte sent),
# backlight and green on the other port extender (second byte sent)
# bit | green LED | red LED
# -------------------------
#  0  |     1     |   7
#  1  |     2     |   6
#  2  |     3     |   5
#  3  |     4     |   4
#  4  |     5     |   3
#  5  |     6     |   2
#  6  |     7     |   1
#  7  | Backlight |   -

# i.e. data frame organisation is [- R1 R2 R3 R4 R5 R6 R7, BL G7 G6 G5 G4 G3 G2 G1]
# Examples:
# 0b01111111,0b11111111 puts all LEDs on
# 0b00000000,0b10000000 puts only backlight on
# 0b01111111,0b10000000 puts all red LEDs and backlight on
class LED(object):
    def __init__(self):
        self.led_port   = 0             ## SPI port where LED shift register is connected
        self.led_CS     = 1             ## chip select whehre LED shift register is connected
        self.led_enable = 4             ## GPIO connected to the LED shift register enable pin
        self.led_data   = ([0,0])       ## contains data to send to LED shift register
        self.backlight  = 1             ## per default backlight is activated
        GPIO.setup(self.led_enable, GPIO.OUT) ## configure pin as output
        GPIO.output(self.led_enable, False)   ## enables LED output on GPIO4 (low active)
        self.spi_led    = spidev.SpiDev()  ## create SPI LED object
        self.display()                  ## set all LEDs off
        ## dictionary for green led settings
        self.green_leds = { 0:0b00000000, 1:0b00000001, 2:0b00000011, 3:0b00000111,
                            4:0b00001111, 5:0b00011111, 6:0b00111111, 7:0b01111111 }
        ## dictionary for red led settings
        self.red_leds   = { 0:0b00000000, 1:0b01000000, 2:0b01100000, 3:0b01110000,
                            4:0b01111000, 5:0b01111100, 6:0b01111110, 7:0b01111111 }

    ## sets the right bits for the required number of LEDs
    #  allowed values for color: green, red, backlight
    #  allowed level range: 0..7
    def set_led(self, color, level):
        if (level > 7): level = 7   ## prevents against illegal values
        if (level < 0): level = 0

        if (color == 'green'):
            tmp_greens       = int(self.led_data[1])             ## saves backlight led status
            green_leds       = self.green_leds.get(level)   ## sets leds according to requested level
            self.led_data[1] = (tmp_greens&0x80)|green_leds ## keep backlight bit, flush old led status, add new status
        if (color == 'red'):
            self.led_data[0] = self.red_leds.get(level)     ## sets leds according to requested level
        if (color == 'backlight'):
            tmp_greens       = self.led_data[1]             ## saves green led status
            self.backlight   = 0 if (level == 0) else 1     ## activate backlight when level > 0
            self.led_data[1] = (tmp_greens&0x7F)|(self.backlight<<7)    ## reset backlight bit and set according to 'level'

    ## displays the configured LEDs
    def display(self):
        xfer_data = self.led_data.copy()    ## prevent xfer2 from deleting the led_data list
        self.spi_led.open(self.led_port,self.led_CS) ## /CS1 addresses LED serial register
        self.spi_led.xfer2(xfer_data,3900000,10,8)    ## list of data, xfer speed, us delay, bits per word
        self.spi_led.close()
        GPIO.output(self.led_enable, False)   ## enables LED output on GPIO4 (low active)

    ## disables LED display
    def disable(self):
        GPIO.output(self.led_enable, True)   ## disables LED output on GPIO4 (low active)
#------------------------- LED class --------------------------------------------------------------

########################## CGLCD class ############################################################
## this class contains all functions for communication with the CGLCD (e.g. ILI9341 based)
#  requires: spidev for communication via SPI interface (i.e. "import spidev" in your source file)
#            RPi.GPIO for talking to GPIO pins (i.e. "import RPi.GPIO as GPIO" in your source file)
# uncomment the lines below if not done yet in your source file
# import spidev
# import RPi.GPIO as GPIO
# # which mode to address GPIOs (BCM: GPIO number, BOARD: connector pin number)
# GPIO.setmode(GPIO.BCM)
class CGLCD(object):
    def __init__(self):
        self.width     = 320        ## number of horizontal physical pixels
        self.height    = 240        ## number of vertical physical pixels
        self.colormode = "16bit"    ## alternative color mode is "18bit"
        ##! self.pages     = 8      ## number of pages for vertical resulution (8px per page for UC1701)
        self.glcd_port = 0          ## SPI port of connected GLCD
        self.glcd_CS   = 0          ## chip select connected to your GLCD CS pin (either 0 or 1)
        self.glcd_RST  = 6          ## GPIO connected to your GLCD reset pin
        GPIO.setup(self.glcd_RST, GPIO.OUT) ## configure pin as output
        self.glcd_RS   = 5          ## GPIO connected to your GLCD data/instruction pin
        GPIO.setup(self.glcd_RS, GPIO.OUT)  ## configure pin as output

        self.lcd_image_data = [0]*int(self.width*self.height*2) ## contains the datastream to send to the LCD
        self.spi_cglcd  = spidev.SpiDev() ## create SPI GLCD object
        self.reset()

    # send command byte to GLCD
    def send_command(self, glcd_command):
        self.spi_cglcd.open(self.glcd_port,self.glcd_CS)
        GPIO.output(self.glcd_RS, False)  # 0 = instruction mode
        self.spi_cglcd.xfer2(glcd_command,3900000,10,8) # list of data, xfer speed, us delay, bits per word
        self.spi_cglcd.close()

    # send data byte to GLCD
    def send_data(self, glcd_data):
        self.spi_cglcd.open(0,0)               # /CS0 addresses LCD serial input
        GPIO.output(self.glcd_RS, True)   # 1 = data mode
        self.spi_cglcd.xfer3(glcd_data,15600000,3,8) # list of data, xfer speed, us delay, bits per word
        self.spi_cglcd.close()

    # perform hardware reset for GLCD
    def reset(self):
        GPIO.output(self.glcd_RST, False)   ## set output low, force reset condition
        time.sleep(0.5)                     ## wait half a second
        GPIO.output(self.glcd_RST, True)    ## release reset condition
        time.sleep(0.01)                    ## wait some time before continuing

    ## initializes the GLCD
    def init(self):
        self.send_command([0x01])       ## soft reset of display
        time.sleep(0.007)               ## mandatory wait after soft reset >= 5 ms

        # the values below are taken from Adafruit ILI9341 pyhton script init section

        self.send_command([0xC0])       ## power control 1
        self.send_data([0x23])          ## GVDD level; default 0x26: 4.95 V; 0x23: 4.60 V
        #self.send_data([0x00])          ## controls VCI1 voltage; default 0x00: 2.30 V; 0x0F is max 3.00 V

        #self.send_command([0xC1])       ## power control 2
        #self.send_data([0x10])          ## step up circuit factor, reduces power consumption; default 0x00: no reduction; 0x07 is max

        self.send_command([0xC5])       ## VCOM control 1
        self.send_data([0x3E])          ## VCOMH voltage, default 0x31:  3.925 V; 0x3E:  4.25 V
        self.send_data([0x28])          ## VCOML voltage, default 0x3C: -1.000 V; 0x28: -1.50 V

        self.send_command([0xC7])       ## VCOM control 2
        self.send_data([0x86])          ## set VCOM offset voltage; default 0xC0: no offset; 0x86: enable VMF setting, set VMH&VML to -58

        self.send_command([0x36])       ## memory access control; required according to mounting direction of the display
        self.send_data([0b00101000])    ## scan direction; 0x00: no change; 0x28(0b00101000): rotate clockwise (landscape mode), BGR color order

        self.send_command([0x3A])       ## set pixel format (color mode)
        if (self.colormode == "16bit"):
            self.send_data([0x55])      ## 0x55 for 16 bit color mode
        else:
            self.send_data([0x66])      ## 0x66 for 18 bit color mode (default)

        self.send_command([0xB1])       ## frame rate control
        self.send_data([0x00])          ## default 0x00: division ratio 1
        self.send_data([0x18])          ## default 0x1B: 70 Hz; 0x18: 79 Hz; lower values give higher frame rates and vice versa

        self.send_command([0xB6])       ## display function control
        self.send_data([0x08])          ## default 0x0A: interval scan, AGND to non-display area in partial mode
        self.send_data([0x82])          ## default 0x82: normally black display, increasing gate scan, 5 frames scan cycle for non-display area
        self.send_data([0x27])          ## default 0x27: 320 display lines

        #self.send_command([0x26])       ## set Gamma curve
        #self.send_data([0x01])          ## default 0x01: G2.2

        self.send_command([0xE0])       ## set gray scale voltage for Gamma adjustment
        self.send_data([0x0F])          ## default 0x0F
        self.send_data([0x31])          ## default 0x22
        self.send_data([0x2B])          ## default 0x1F
        self.send_data([0x0C])          ## default 0x0A
        self.send_data([0x0E])          ## default 0x0E
        self.send_data([0x08])          ## default 0x06
        self.send_data([0xeE])          ## default 0x4D
        self.send_data([0xF1])          ## default 0x76
        self.send_data([0x37])          ## default 0x3B
        self.send_data([0x07])          ## default 0x03
        self.send_data([0x10])          ## default 0x0E
        self.send_data([0x03])          ## default 0x04
        self.send_data([0x0E])          ## default 0x13
        self.send_data([0x09])          ## default 0x0E
        self.send_data([0x00])          ## default 0x0C

        self.send_command([0xE1])        ## set gray scale voltage for Gamma adjustment
        self.send_data([0x00])          ## default 0x0C
        self.send_data([0x0E])          ## default 0x23
        self.send_data([0x14])          ## default 0x26
        self.send_data([0x03])          ## default 0x04
        self.send_data([0x11])          ## default 0x10
        self.send_data([0x07])          ## default 0x04
        self.send_data([0x31])          ## default 0x39
        self.send_data([0xC1])          ## default 0x24
        self.send_data([0x48])          ## default 0x4B
        self.send_data([0x08])          ## default 0x03
        self.send_data([0x0F])          ## default 0x0B
        self.send_data([0x0C])          ## default 0x0B
        self.send_data([0x31])          ## default 0x33
        self.send_data([0x36])          ## default 0x37
        self.send_data([0x0F])          ## default 0x0F

        self.send_command([0x11])       ## exit sleep mode
        time.sleep(0.150)               ## requires >= 120 ms for transition from sleep

        self.send_command([0x13])       ## normal display mode on
        self.send_command([0x29])       ## display on (after reset it is off)

        self.send_command([0x20])       ## display inversion off  (inversion on: 0x21)

        #self.send_command([0x2D])       ## Color set command, following data fills LUT for 16->18 bit conversion


    ## converts 24 bit colors to the desired color mode
    #  16 bit mode fits into 2 bytes: rrrrrggg gggbbbbb
    #  18 bit mode fits into 3 bytes: rrrrrr00 gggggg00 bbbbbb00
    def convert_colors(self, colors):   ## input is a tuple containig (red, green, blue)
        red, green, blue = colors
        if (self.colormode == "16bit"): ## convert to 5 Bit red, 6 Bit green, 5 Bit blue
            value1 = (0b11111000&(red))|(0b00000111&(green>>5))     ## use 5 highest bits from red value, take highest 3 bits from green
            value2 = (0b11100000&(green<<3))|(0b00011111&(blue>>3)) ## use bits 5,4,3 from green, use highest 5 bits from blue
            return ([value1,value2])
        else: ## convert to 6 bit red, 6 bit green, 6 bit blue
            value1 = 0b11111100&red     ## use 6 highest bits from red
            value2 = 0b11111100&green   ## use 6 highest bits from green
            value3 = 0b11111100&blue    ## use 6 highest bits from blue
            return ([value1,value2,value3])

    ## converts image to data stream for CGLCD output
    def convert_image(self, image):
        pixels = image.load() ## get image data for conversion

        # put pixels to the LCD required format: for 16 bit colors 2 bytes with 3 color values, for 18 bit 3 bytes (1 byte for each color)
        # all pixels for the display are a single data stream
        if(self.colormode == "16bit"):
            self.lcd_image_data = [0]*int(image.size[0]*(image.size[1])*2) # contains the datastream to send to the LCD
        else:
            self.lcd_image_data = [0]*int(image.size[0]*(image.size[1])*3) # contains the datastream to send to the LCD

        index = 0
        for line in range (self.height):
            # scan all columns for the current line
            for col in range (self.width):
                colordata = self.convert_colors(pixels[col,line])
                for byte in range (len(colordata)):
                    self.lcd_image_data[index] = colordata[byte]
                    index += 1

    def display(self):
        import datetime
        thisdate = str(datetime.datetime.now()).partition('.')[0] ## for error message time stamp

        ## send image to display
        ## spidev allows a maximum of 4096 bytes as argument
        displayimage = self.lcd_image_data.copy()  ## prevent list from being altered while sending data
        self.send_command([0x2C]) ## write to RAM, that's how the pixel data arrives at the LCD

        self.send_data(displayimage)
#------------------------- GLCD class --------------------------------------------------------------

########################## Canvas class ############################################################
## this class contains all functions to provide the image that will be displayed on the GLCD
#  .canvas contains the image that must be converted for display on GLCD
class Canvas(object):
    def __init__(self):
        ## provides functions for image creation for GLCD
        try:
            from PIL import Image, ImageDraw, ImageFont
        except:
            try: ## for command line showerror does not work
                messagebox.showerror('Import Error','pillow package was not found on your system.\nPlease install it using the command:\
                                \n"pip install pillow"')
            except:
                print('Import errror. pillow package was not found on your system. Please install it using the command: "pip install pillow"')
        self.canvas_width  = cglcd.width
        self.canvas_height = cglcd.height
        self.fontname   = "LCD_Solid.ttf"
        self.font       = ImageFont.truetype(self.fontname,14)
        self.smallfont  = ImageFont.truetype(self.fontname,10)
        self.bigfont    = ImageFont.truetype(self.fontname,36)
        self.canvas     = Image.new('RGB', (self.canvas_width, self.canvas_height)) ## create RGB image
        self.drawing    = ImageDraw.Draw(self.canvas)
        self.drawing.rectangle((0,0,self.canvas_width-1,self.canvas_height-1),outline=(0,0,0), fill=(0xff,0xff,0xff)) #blank box to clear display

#------------------------- Canvas class ------------------------------------------------------------

########################## Data class ##############################################################
## class for all data related things
#
class Data(object):
    ## set default values and allowed input values
    def __init__(self):
        self.inifilename = None
        self.ipaddress = '10.0.0.42'    ## address of the communication target
        self.portno =   502             ## port number of the target
        self.modbusid = 3               ## bus ID of the target
        self.manufacturer = 'Default Manufacturer' ## arbitrary string for user convenience
        self.loginterval = 5            ## how often should data be pulled from target in seconds
        self.moddatatype = {            ## allowed data types, sent from target
                'S32':2,
                'U32':2,
                'U64':4,
                'STR32':16,
                'S16':1,
                'U16':1
                }

        self.dataformat = ['ENUM','UTF8','FIX3','FIX2','FIX1','FIX0','RAW'] ## data format from target

        ## table of data to be pulled from target
        self.datasets = [['address','type','format','description','unit','value']]

        self.datavector = []        ## holds the polled data from target
        self.databuffer = []        ## holds the datavectors before writing to disk
        self.datawritebuffer = []   ## holds data before printing to LCD
#------------------------- Data class --------------------------------------------------------------

########################## Inout class #############################################################
## class that contains all IO specifics
class Inout:
    import RPi.GPIO as GPIO ## required for clean program exit

    ## some values to check against when receiving data from target
    #  these values are read when there is not acutal value from the target available.
    #  they are the equivalent to None
    MIN_SIGNED   = -2147483648
    MAX_UNSIGNED =  4294967295
    running_on_RPi = True
    color_bk  = (0,0,0)
    color_wt  = (0xff,0xff,0xff)
    color_rd  = (0xff,0,0)
    color_gn  = (0,0xff,0)
    color_yl  = (0xff,0xff,0)
    color_or  = (0xff,0x7f,0)
    color_dgn = (0,0x9a,0)
    color_lbl = (0xca,0xda,0xff)
    message_errorcounter = 0     ## holds the count for data receive errors

    import time

    ## function for testing the per command line specified configuration file
    def checkImportFile(self):
        ## does the file exist?
        try:
            inifile = open(str(arguments['--inifile']),'r').close()
            data.inifilename = str(arguments['--inifile'])
        except:
            ## if we have a GUI display an error dialog
            try:
                showerror('Import Error','The specified configuration file was not found.')
                return
            except: ## if no GUI display error and exit
                print('Configuration file error. A file with that name seems not to exist, please check.')
                exit()
        try:
            inout.readImportFile()
        except:
            try:
                showerror('Import Error','Could not read the configuration file. Please check file path and/or file.')
                return
            except:
                print('Could not read configuration file. Please check file path and/or file.')
                exit()

    ## function for acually reading input configuration file
    def readImportFile(self):
        ## read config data from file
        import configparser
        Config = configparser.ConfigParser()
        ## read the config file
        Config.read(data.inifilename, encoding="utf-8")
        data.ipaddress     = Config.get('CommSettings','IP address')
        data.portno        = int(Config.get('CommSettings','port number'))
        data.modbusid      = int(Config.get('CommSettings','Modbus ID'))
        data.manufacturer  = Config.get('CommSettings','manufacturer')
        data.loginterval   = int(Config.get('CommSettings','logger interval'))
        data.datasets      = eval(Config.get('TargetDataSettings','data table'))

    ## function for actually writing configuration data
    #
    def writeExportFile(self):
        import io ## required for correct writing of unicode characters to file
        ## use ini file capabilities
        import configparser
        Config = configparser.ConfigParser()

        ## if the dialog was closed with no file selected ('cancel') just return
        if (data.inifilename == None):
            try: ## if running in command line no window can be displayed
                showerror('Configuration File Error','no file name given, please check.')
            except:
                print('Configuration file error, no file name given, please check.')
            return
        ## write the data to the selected config file
        try:
            inifile = io.open(data.inifilename,'w',encoding="utf-8")
        except:
            try: ## if running in command line no window can be displayed
                showerror('Configuration File Error','a file with that name seems not to exist, please check.')
            except:
                print('Configuration file error, a file with that name seems not to exist, please check.')
            gui.selectExportFile()
            return

        ## format the file structure
        Config.add_section('CommSettings')
        Config.set('CommSettings','IP address',str(data.ipaddress))
        Config.set('CommSettings','port number',str(data.portno))
        Config.set('CommSettings','Modbus ID',str(data.modbusid))
        Config.set('CommSettings','manufacturer',str(data.manufacturer))
        Config.set('CommSettings','logger interval',str(data.loginterval))
        Config.add_section('TargetDataSettings')
        Config.set('TargetDataSettings','data table',str(data.datasets))

        Config.write(inifile)
        inifile.close()

## function for writing to LCD and LED

    def writeLoggerDataLCD(self):
        import datetime
        import math ## required for Pi and log10 function

        ## collect current time to display
        thistime = datetime.datetime.now().strftime("%H:%M")

        ## format the data for the display before actually sending to LCD
        if (data.datawritebuffer[0][0] != None): ## at night there is no dc power
            dc_watts   = str(data.datawritebuffer[0][0]) #.ljust(4)
        else:
            dc_watts = str(0)
        if (data.datawritebuffer[0][1] != None): ## at night there is no ac power
            ac_watts = str(data.datawritebuffer[0][1])
            ac_watts_i = (data.datawritebuffer[0][1])
        else:
            ac_watts = str(0)
            ac_watts_i = 0
        if (data.datawritebuffer[0][2] != None): ## at night there is no dc voltage
            dc_volts = str(int(data.datawritebuffer[0][2]))
        else:
            dc_volts = str(0)
        if (data.datawritebuffer[0][3] != None): ## at night there is no yield
            e_wh     = str(data.datawritebuffer[0][3])
        else:
            e_wh     = str(0)
        p_in_wa  = str(data.datawritebuffer[0][4])
        p_in_w   = str(p_in_wa+" W")
        if (data.datawritebuffer[0][4] != None): ## at night there is no output
            p_out_w = str(data.datawritebuffer[0][5])
        else:
            p_out_w = str(0)
        #   current load is a calculated value:= DC_power + Power_from_grid - Power_to_grid
        load_wa_i = (int(float(ac_watts)) + int(float(p_in_wa)) - int(float(p_out_w)))
        load_wa   = str(load_wa_i)
        load_w    = str(load_wa+" W").ljust(7)

        ##   LCD layout in text mode:
        #   E: xxxxx W   DC: xxx V
        #   AC: xxxx W P->: xxxx W
        #   P<-: xxxxx W
        #   Load: xxxxx W
        #                    HH:MM
        if (disp_graphical==0): ## text-only mode
            canvas.drawing.rectangle((0,0,canvas.canvas_width-1,canvas.canvas_height-1),outline=self.color_bk, fill=self.color_wt) ## clear cavas before updating
            canvas.drawing.text((1,1), "E: "+e_wh+" Wh",font=canvas.font,fill=self.color_bk)    ## first data line
            canvas.drawing.text((100,1),"DC: "+dc_volts+" V",font=canvas.font,fill=self.color_bk)    ## first data line
            canvas.drawing.text((1,20),"AC: "+ac_watts+" W", font=canvas.font, fill=self.color_or) ## second line
            canvas.drawing.text((100,20),"P-> "+p_out_w+" W", font=canvas.font, fill=self.color_gn) ## second line
            canvas.drawing.text((1,40),"P<- "+p_in_wa+" W", font=canvas.font, fill=self.color_rd)
            canvas.drawing.text((1,60),"Last: "+load_wa+" W", font=canvas.font, fill=self.color_bk)
            canvas.drawing.text((265,220),thistime, font=canvas.font, fill=self.color_bk)
        else: ## graphical display mode
            ## we want ticks for some load values: e.g. 0, 0.1,.. 0.9, 1, 2, ... 10 kW
            #  with log10 this provides exactly the desired output ticks
            #  for other values (lower 0.1, higher 10) scaling must be modified
            #
            ## arcs and pieslices are drawn clockwise in contrast to mathematical angles
            #  so we convert the tics to the desired end angles
            #  scale is logarithmic: full scale = 180° -> 10 kW
            #                        half scale = 90°  ->  1 kW
            #  math angle functions work with Pi arguments,
            #  we need to convert to degrees for arc and pieslice
            #  to achieve left to right scale movement end angles must be negative
            #
            # Example for calculation:
            #          +- draw upper half of circle
            #          |       +- Pi/2 equals the 1 (kW) mark,
            #          |       |  values lower than 1 give negative
            #          |       |  log10() results,
            #          |       |  higher values give positve results
            #          |       |  "subtracting" from Pi/2 gives the desired
            #          |       |  results
            #          |       |                 +- get the log10 value for
            #          |       |                 |  the given power value
            #          |       +-----+           |           +- convert to
            #          |       |     |           |           |  degrees
            #          |       |     |        ___|___    ____|_____
            #          v       v     v       /       \  /          \
            # tick02 = -((math.pi/2*(1-math.log10(0.6)))/math.pi*180)
            # tick02 -> -118

            ## provide values for tick marks in kW
            ticks = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

            tick_angles = []  ## holds the angles for the desired tick marks
            for tick in range (len(ticks)):
                if (ticks[tick]!=0): ## log10 is not defined for 0
                    angle = -((math.pi/2*(1-math.log10(ticks[tick])))/math.pi*180)
                else:
                    angle = -180  ## 0 tick will be equal to 180° position
                tick_angles.append(int(angle))

            bbox  = [30,43,290,290] ## bounding box for arc and pieslice
            tbbox = [27,40,293,293] ## bounding box for tics on arc

            canvas.drawing.rectangle((0,0,canvas.canvas_width-1,canvas.canvas_height-1),outline=self.color_bk, fill=self.color_lbl) ## clear cavas before updating

            ## draw ticks
            ## we need to draw ticks for the highest values first,
            #  otherwise the lower value ticks will be overwritten by
            #  higher value drawing operations
            tick_angles.reverse()
            for tick in range (len(tick_angles)):
                canvas.drawing.pieslice(tbbox,180,tick_angles[tick],fill=self.color_lbl,outline=self.color_bk) ## draw pieslice for tick
                canvas.drawing.arc(tbbox,180,tick_angles[tick],fill=self.color_lbl) ## "delete" arc from pieslice

            ## clear graph area (e.g. artefacts from tick creation)
            canvas.drawing.pieslice(bbox,180,0,fill=self.color_wt,outline=self.color_bk)

            ## draw graph
            canvas.drawing.arc(bbox,180,0,fill=self.color_bk) ## draw scale outline for yield and consumption

            canvas.drawing.text([15,162],"0",font=canvas.smallfont,fill=self.color_bk)       ## tick label for 0
            canvas.drawing.text([23,99],"0.1",font=canvas.smallfont,fill=self.color_bk)     ## tick label for 0.1
            canvas.drawing.text([158,27],"1 kW",font=canvas.smallfont,fill=self.color_bk)       ## tick label for 1 kW
            canvas.drawing.text([295,162],"10 kW",font=canvas.smallfont,fill=self.color_bk) ## tick label for 10 kW

            ## calculate angle for consumption and yield, normalize to 1 kW
            ac_watts_disp   = ac_watts_i/1000.0
            load_watts_disp = load_wa_i/1000.0
            ## for values < 0.9 kW adding 0.1 for display purposes,
            #  otherwise values < 100 W cannot be displayed on the graph
            #  between 900 W and 1 kW there is so small space between the ticks,
            #  so thats not a problem display-wise
            if (ac_watts_disp   < 1):
                ac_watts_disp   = ac_watts_disp*0.9+0.1
            if (load_watts_disp < 1):
                load_watts_disp = load_watts_disp*0.9+0.1
            ## making sure no values smaller 0.1 are fed to log10
            if (ac_watts_disp   <= 0):
                ac_watts_disp   = 0.1
            if (load_watts_disp <= 0):
                load_watts_disp = 0.1
            ## for display purposes capping display at 10 kW
            if (ac_watts_disp   >= 10.0):
                ac_watts_disp   = 10.0
            if (load_watts_disp >= 10.0):
                load_watts_disp = 10.0

            yield_angle = int(-((math.pi/2*(1-math.log10(ac_watts_disp)))/math.pi*180))
            load_angle  = int(-((math.pi/2*(1-math.log10(load_watts_disp)))/math.pi*180))
            if (yield_angle >= load_angle): ## draw larger value first
                ## if yield is higher than load, load pie will be displayed yellow
                canvas.drawing.pieslice(bbox,180,yield_angle,fill=self.color_gn,outline=self.color_bk) ## graph for yield, filled green
                canvas.drawing.pieslice(bbox,180,load_angle,fill=self.color_yl, outline=self.color_bk) ## graph for consumption, filled yellow
            else:
                ## if load is higher than load, load pie will be displayed red
                canvas.drawing.pieslice(bbox,180,load_angle,fill=self.color_rd,outline=self.color_bk) ## graph for consumption, filled red
                canvas.drawing.pieslice(bbox,180,yield_angle,fill=self.color_yl,outline=self.color_bk) ## graph for yield, filled yellow

            ## sun symbol for yield value, display color orange
            sun_offset=[8,8] ## top left corner of bounding box
            canvas.drawing.line([sun_offset[0]+1,sun_offset[1]+1,sun_offset[0]+9,sun_offset[1]+9],fill=self.color_or, width=1)
            canvas.drawing.line([sun_offset[0]+9,sun_offset[1]+1,sun_offset[0]+1,sun_offset[1]+9],fill=self.color_or, width=1)
            canvas.drawing.line([sun_offset[0]+5,sun_offset[1],  sun_offset[0]+5,sun_offset[1]+10],fill=self.color_or, width=1)
            canvas.drawing.line([sun_offset[0],  sun_offset[1]+5,sun_offset[0]+10,sun_offset[1]+5],fill=self.color_or, width=1)
            canvas.drawing.ellipse([sun_offset[0]+3,sun_offset[1]+3,sun_offset[0]+8,sun_offset[1]+8], fill=self.color_yl, outline=self.color_or)

            ## solar power value
            canvas.drawing.text([20,7],(ac_watts+" W"),fill=self.color_dgn,font=canvas.font)

            ## power direction value
            power_txt = (p_in_wa + " W") if (int(float(p_in_wa)) > 0) else (p_out_w + " W")
            twidth, theight = canvas.drawing.textsize(power_txt)
            canvas.drawing.text([290-twidth,7],power_txt,fill=self.color_rd if (int(float(p_in_wa))>0) else self.color_dgn,font=canvas.font)

            ## house symbol
            canvas.drawing.polygon([257,43, 257,34, 265,26, 273,34, 273,43, 257,43],fill=self.color_bk)

            if (int(float(p_out_w))>0): ## power into grid
                ## right pointing arrow, display color darker green
                canvas.drawing.polygon([283,39, 283,39, 290,33, 290,29, 300,36, 290,43, 290,39, 283,39], fill=self.color_dgn)
            else:  ## feed from grid
                ## left pointing arrow, display color red
                canvas.drawing.polygon([300,39, 300,33, 293,33, 293,29, 283,36, 293,43, 293,39, 300,39], fill=self.color_rd)

            ## current load
            load_txt = (load_wa+" W")
            twidth, theight = canvas.drawing.textsize(load_txt, font=canvas.bigfont) ## get text area for background fill
            graph_x_center=(bbox[0]+bbox[2])/2      ## calculate center for centered placement
            canvas.drawing.rectangle([graph_x_center-twidth/2-1,180,graph_x_center+twidth/2,180+theight-1],fill=self.color_lbl) ## background fill
            canvas.drawing.text([graph_x_center-twidth/2,180],load_txt,fill=self.color_bk,outline=self.color_bk,font=canvas.bigfont) ## place load value on graph

            ## daily energy yield on bottom left
            canvas.drawing.text([3,220],("E: "+e_wh+" Wh"),font=canvas.font, fill=self.color_bk)

            ## current time on bottom right
            canvas.drawing.text((265,220),thistime, font=canvas.font, fill=self.color_bk)


        ## send data to display
        cglcd.convert_image(canvas.canvas)
        cglcd.display()

        ## formats led data
        #  there a 7 LEDs that provide fast overview of load/PV yield
        #  scaling is done in logarithmic steps:
        #  50W, 120W, 230W, 450W, 830W, 1400W, 2200W.
        ## first set green leds for PV yield
        if (ac_watts_i > 2200):
            led.set_led("green", 7)
        elif (ac_watts_i > 1400):
            led.set_led("green", 6)
        elif (ac_watts_i > 830):
            led.set_led("green", 5)
        elif (ac_watts_i > 450):
            led.set_led("green", 4)
        elif (ac_watts_i > 230):
            led.set_led("green", 3)
        elif (ac_watts_i > 120):
            led.set_led("green", 2)
        elif (ac_watts_i > 60):
            led.set_led("green", 1)
        else:
            led.set_led("green", 0)

        ## set red LEDs for power consumption
        if (load_wa_i > 2200):
            led.set_led("red", 7)
        elif (load_wa_i > 1400):
            led.set_led("red", 6)
        elif (load_wa_i > 830):
            led.set_led("red", 5)
        elif (load_wa_i > 450):
            led.set_led("red", 4)
        elif (load_wa_i > 230):
            led.set_led("red", 3)
        elif (load_wa_i > 120):
            led.set_led("red", 2)
        elif (load_wa_i > 60):
            led.set_led("red", 1)
        else:
            led.set_led("red", 0)

        ## updates LEDs to current load status
        led.display()

#------------ END LCD functions -----------------------------------------------------------------

    ## function for starting communication with target
    #
    def runCommunication(self):
        from pymodbus.client.sync import ModbusTcpClient as ModbusClient

        self.client = ModbusClient(host=data.ipaddress, port=data.portno)
        try:
            self.client.connect()
        except:
            try:
                tk.showerror('Modbus Connection Error','could not connect to target. Check your settings, please.')
            except:
                print('Modbus Connection Error. Could not connect to target. Check your settings, please.')

        self.pollTargetData()

        self.client.close()
        ## lambda: is required to not spawn hundreds of threads but only one that calls itself
        self.commtimer = Timer(float(data.loginterval), lambda: self.runCommunication())
        self.commtimer.start() ## needs to be a separate command else the timer is not cancel-able

    def stopCommunication(self):
        self.commtimer.cancel()

    ## function for polling data from the target and triggering writing to LCD
    #   data to be polled is provided in fixed ini-file to enable fixed LCD layout
    #   data order in ini-file: DC power [W], AC power [W], DC input voltage [V],
    #                           daily yield [Wh], power from Grid [W], power to Grid [W]
    #   current load is a calculated value:= DC_power - Power_to_grid + Power_from_grid
    #
    def pollTargetData(self):
        from pymodbus.payload import BinaryPayloadDecoder
        from pymodbus.constants import Endian
        import datetime

        data.datavector = [] ## empty datavector for current values
        thisdate = str(datetime.datetime.now()).partition('.')[0] ## for error message time stamp

        ## request each register from datasets, omit first row which contains only column headers
        for thisrow in data.datasets[1:]:
            ## if the connection is somehow not possible (e.g. target not responding)
            #  show a error message instead of excepting and stopping
            try:
                received = self.client.read_input_registers(address = int(thisrow[0]),
                                                     count = data.moddatatype[thisrow[1]],
                                                      unit = data.modbusid)
            except:
                thiserrormessage = thisdate + ': Connection not possible. Check settings or connection.'
                if (gui_active):
                    messagebox.showerror('Connection Error',thiserrormessage)
                    return  ## prevent further execution of this function
                else:
                    print(thiserrormessage)
                    return  ## prevent further execution of this function

            ## if somehow the received data is not what the interpreter expexts
            try:
                if not received.isError():
                    message = BinaryPayloadDecoder.fromRegisters(received.registers, byteorder=Endian.Big, wordorder=Endian.Big)
                    self.message_errorcounter = 0
                if received.isError():
                    self.message_errorcounter += 1
                    print (thisdate,' Receive error! Error count: ',str(self.message_errorcounter))
                    return ## no valid data, do nothing
            except:
                self.message_errorcounter += 1
                thiserrormessage = thisdate + ': Received data not valid. Error count:' + str(self.message_errorcounter)
                print ("Received is: ", received)
                if (gui_active):
                    messagebox.showerror('Data Error',thiserrormessage)
                    return  ## prevent further execution of this function
                else:
                    print(thiserrormessage)
                    return  ## prevent further execution of this function

            ## provide the correct result depending on the defined datatype
            if thisrow[1] == 'S32':
                interpreted = message.decode_32bit_int()
            elif thisrow[1] == 'U32':
                interpreted = message.decode_32bit_uint()
            elif thisrow[1] == 'U64':
                interpreted = message.decode_64bit_uint()
            elif thisrow[1] == 'STR32':
                interpreted = message.decode_string(32).decode("utf-8").strip('\x00') ## convert bytes to str
            elif thisrow[1] == 'S16':
                interpreted = message.decode_16bit_int()
            elif thisrow[1] == 'U16':
                interpreted = message.decode_16bit_uint()
            else: ## if no data type is defined do raw interpretation of the delivered data
                interpreted = message.decode_16bit_uint()

            ## check for "None" data before doing anything else
            if ((interpreted == self.MIN_SIGNED) or (interpreted == self.MAX_UNSIGNED)):
                displaydata = None
            else:
                ## put the data with correct formatting into the data table
                if thisrow[2] == 'FIX3':
                    displaydata = float(interpreted) / 1000
                elif thisrow[2] == 'FIX2':
                    displaydata = float(interpreted) / 100
                elif thisrow[2] == 'FIX1':
                    displaydata = float(interpreted) / 10

                else:
                    displaydata = interpreted

            ## save _scaled_ data in datavector for further handling
            data.datavector.append(displaydata)

        ## display collected data
        if (gui_active == 1):
            gui.updateLoggerDisplay()

        ## save collected data to buffer
        data.databuffer.append(data.datavector)

        ## ensure that the data to write will not be altered by faster poll cycles
        data.datawritebuffer = data.databuffer
        data.databuffer = [] ## empty the buffer
        self.writeLoggerDataLCD() ## call write routine to print data on LCD

    ## function adds dataset to the datasets list
    #   also updates the displayed list
    #   new datasets are not added to the config file
    #
    def addDataset(self,inputdata):
        data.datasets.append(inputdata)
        print('Current datasets: ',(data.datasets))

    ## function for saving program state at program exit
    #
    def cleanOnExit(self):
        try: ## stop data logging on exit, catch a possible exception, when communication is not running
            self.stopCommunication()
        except:
            print ('')

        led.led_data=([0x00,0x00]) # transfer all '0' for all LED off
        led.display()
        self.GPIO.cleanup()
        print('PyModMonLCD has exited cleanly.')

    ## function for printing the current configuration settings
    #   only used for debug purpose
    #
    def printConfig(self):
        counter = 0
        for data in data.datasets:
            print('Datasets in List:', counter, data)
            counter += 1
#------------------------- InOut class --------------------------------------------------------------

########################## GUI class ###############################################################
## class that contains all GUI specifics
#
class Gui:
    def __init__(self,master):

        ## configure app window
        master.title('Python Modbus Monitor LCD')
        master.minsize(width=550, height=450)
        master.geometry("550x550")  ## scale window a bit bigger for more data lines
        self.settingscanvas = tk.Canvas(master,bg="yellow",highlightthickness=0)
        self.settingscanvas.pack(side='top',anchor='nw',expand=False,fill='x')

        ## make the contents of settingscanvas fit the window width
        tk.Grid.columnconfigure(self.settingscanvas,0,weight = 1)

        ## create window containers

        ## frame for the config file and data logger file display
        filesframe = tk.Frame(self.settingscanvas,bd=1,relief='groove')
        filesframe.columnconfigure(1,weight=1) ## set 2nd column to be auto-stretched when window is resized
        filesframe.grid(sticky = 'EW')

        ## frame for the settings of the communication parameters
        self.settingsframe = tk.Frame(self.settingscanvas,bd=1,relief='groove')
        self.settingsframe.grid(sticky = 'EW')

        ## frame for the controls for starting and stopping configuration
        controlframe = tk.Frame(self.settingscanvas,bd=1,relief='groove')
        controlframe.grid(sticky = 'EW')

        ## create Menu
        menubar = tk.Menu(master)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label='Import Configuration File…',command=self.selectImportFile)
        filemenu.add_command(label='Export Configuration File…',command=self.selectExportFile)
        filemenu.add_command(label='Save Current Configuration',command=inout.writeExportFile)
        filemenu.add_command(label='Exit',command=self.closeWindow)

        toolmenu = tk.Menu(menubar, tearoff=0)
        toolmenu.add_command(label='Data Settings…',command=self.dataSettings)
        toolmenu.add_command(label='Print Config Data',command=inout.printConfig)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label='About…',command=self.aboutDialog)

        menubar.add_cascade(label='File', menu=filemenu)
        menubar.add_cascade(label='Tools', menu=toolmenu)
        menubar.add_cascade(label='Help', menu=helpmenu)
        master.config(menu=menubar)

        ## add GUI elements

        ## input mask for configuration file
        #
        tk.Label(filesframe, text='Configuration File:').grid(row=0,sticky='E')

        self.input_inifilename = tk.Entry(filesframe, width = 40)
        self.input_inifilename.bind('<Return>',self.getInputFile)   ## enable file name to be set by [Enter] or [Return]
        self.input_inifilename.grid(row=0,column=1,sticky='EW')     ## make input field streching with window

        tk.Button(filesframe,text='…',command=(self.selectImportFile)).grid(row=0,column=2,sticky='W') ## opens dialog to choose file from

        tk.Button(filesframe,text='⟲ Re-Read Configuration', command=(self.displaySettings)).grid(row=3,column=0,sticky='W') ## triggers re-read of the configuration file
        tk.Button(filesframe,text='⤓ Save Current Configuration', command=(inout.writeExportFile)).grid(row=3,column=1,sticky='W') ## triggers re-read of the configuration file

        ## buttons for starting and stopping data retrieval from the addressed target
        #

        ## Button for starting communication and starting writing to logger file
        self.commButton = tk.Button(controlframe,text='▶ Start Communication',bg='lightblue', command=self.startCommunication)
        self.commButton.grid(row=0,column=1,sticky='W')

        ## fields for configuring the data connection
        #
        tk.Label(self.settingsframe, text='Communication Connection Settings', font='-weight bold').grid(columnspan=4, sticky='W')
        tk.Label(self.settingsframe, text='Current Values').grid(row=1,column=1)
        tk.Label(self.settingsframe, text='New Values').grid(row=1,column=2)

        tk.Label(self.settingsframe, text='Target IP Address:').grid(row=2,column=0,sticky = 'E')
        tk.Label(self.settingsframe, text='Port No.:').grid(row=3,column=0,sticky = 'E')
        tk.Label(self.settingsframe, text='Modbus Unit ID:').grid(row=4,column=0,sticky = 'E')
        tk.Label(self.settingsframe, text='Manufacturer:').grid(row=5,column=0,sticky = 'E')
        tk.Label(self.settingsframe, text='Log Interval[s]:').grid(row=6,column=0,sticky = 'E')
        tk.Button(self.settingsframe,text='⮴ Update Settings',bg='lightgreen',command=(self.updateCommSettings)).grid(row=7,column=2, sticky='W')

        ## frame for entering and displaying the data objects
        self.datasettingsframe = tk.Frame(self.settingscanvas,bd=1,relief='groove')
        self.datasettingsframe.columnconfigure(3,weight=1) ## make description field fit the window
        self.datasettingsframe.grid(sticky = 'EW')

        ## table with data objects to display and the received data
        tk.Label(self.datasettingsframe, text='Target Data', font='-weight bold').grid(columnspan=4, sticky='W')
        tk.Label(self.datasettingsframe, text='Addr.').grid(row=1,column=0)
        tk.Label(self.datasettingsframe, text='Type').grid(row=1,column=1)
        tk.Label(self.datasettingsframe, text='Format').grid(row=1,column=2)
        tk.Label(self.datasettingsframe, text='Description').grid(row=1,column=3)
        tk.Label(self.datasettingsframe, text='Unit').grid(row=1,column=4)
        self.input_modaddress = tk.Entry(self.datasettingsframe,width=7)
        self.input_modaddress.grid(row=2,column=0)

        self.input_moddatatype = tk.StringVar()
        self.input_moddatatype.set(list(data.moddatatype.keys())[0])#[0])
        self.choice_moddatatype = tk.OptionMenu(self.datasettingsframe,self.input_moddatatype,*data.moddatatype)
        self.choice_moddatatype.grid(row=2,column=1)

        self.input_dataformat = tk.StringVar()
        self.input_dataformat.set(None)
        self.choice_moddatatype = tk.OptionMenu(self.datasettingsframe,self.input_dataformat,*data.dataformat)
        self.choice_moddatatype.grid(row=2,column=2)

        self.input_description = tk.Entry(self.datasettingsframe,width=35)
        self.input_description.grid(row=2,column=3,sticky='ew')

        self.input_dataunit = tk.Entry(self.datasettingsframe,width=5)
        self.input_dataunit.grid(row=2,column=4)

        tk.Button(self.datasettingsframe,text='+',font='-weight bold',bg='lightyellow',command=(self.addNewDataset)).grid(row=2,column=6)

        ## checkbutton to enable manipulation of the entered data.
        #  this is slow, therefore not enabled by default. Also it alters the display layout.
        self.checked_manage = tk.IntVar()
        self.checkManageData = tk.Checkbutton(self.datasettingsframe,
                                         text='Manage data sets',
                                         variable=self.checked_manage,
                                         command=self.displayDatasets,
                                         )
        self.checkManageData.grid(row=3,column=0,columnspan=3)

        ## canvas for displaying monitored data
        self.datacanvas = tk.Canvas(master,bd=1,bg="green",highlightthickness=0)
        self.datacanvas.pack(anchor='sw',side='top',expand=True,fill='both')
        ## frame that holds all data to display. the static data table and the polled data
        self.dataframe = tk.Frame(self.datacanvas)
        self.dataframe.pack(side='left',expand=True,fill='both')
        ## frame for static data table
        self.datadisplayframe = tk.Frame(self.dataframe,bd=1,relief='groove')
        #self.datadisplayframe = Frame(self.datacanvas,bd=1,relief='groove')
        self.datadisplayframe.pack(side='left', anchor='nw',expand=True,fill='both')
        ## frame for data from target
        self.targetdataframe = tk.Frame(self.dataframe,bg='white',relief='groove',bd=1)
        self.targetdataframe.pack(side='left', anchor='nw',expand=True,fill='both')
        #self.targetdataframe.grid(column=1, row=0)
        ## add scrollbar for many data rows
        self.datascrollbar = tk.Scrollbar(self.datacanvas, orient='vertical', command=self.datacanvas.yview)
        self.datascrollbar.pack(side='right',fill='y')
        #self.datascrollbar = Scrollbar(self.datacanvas, orient='vertical', command=self.datacanvas.yview)
        self.datacanvas.configure(yscrollcommand=self.datascrollbar.set)

        ## make data table fit in scrollable frame
        self.datacanvas.create_window((0,0), window=self.dataframe, anchor='nw',tags='dataframe')

        ## fill the datafields with the current settings
        self.displayCommSettings()
        self.displayDatasets()

        self.update_data_layout()

    ## function for updating the data view after adding content to make the scrollbar work correctly
    def update_data_layout(self):
        self.dataframe.update_idletasks()
        self.datacanvas.configure(scrollregion=self.datacanvas.bbox('all'))

    def displaySettings(self):
        ## read import file and update displayed data
        inout.readImportFile()
        self.displayCommSettings()
        self.displayDatasets()

        ## update displayed filename in entry field
        self.input_inifilename.delete(0,tk.END)
        self.input_inifilename.insert(0,data.inifilename)

    def displayDatasets(self):
        ## display all currently available datasets
        for widget in self.datadisplayframe.winfo_children():
            widget.destroy()

        if (self.checked_manage.get()):
            tk.Label(self.datadisplayframe,text='Up').grid(row=0,column=0)
            tk.Label(self.datadisplayframe,text='Down').grid(row=0,column=1)
            tk.Label(self.datadisplayframe,text='Delete').grid(row=0,column=2)

        thisdata = '' ## make local variable known
        for thisdata in data.datasets:
            counter = data.datasets.index(thisdata) ## to keep track of the current row
            if (self.checked_manage.get()):
                ## add some buttons to change order of items and also to delete them
                if (counter > 1): ## first dataset cannot be moved up
                    buttonUp = tk.Button(self.datadisplayframe,
                                    text='↑',
                                    command=lambda i=counter:(self.moveDatasetUp(i)))
                    buttonUp.grid(row=(counter),column = 0)
                if ((counter > 0) and (counter != (len(data.datasets)-1))): ## last dataset cannot be moved down
                    buttonDown = tk.Button(self.datadisplayframe,
                                      text='↓',
                                      command=lambda i=counter:(self.moveDatasetDown(i)))
                    buttonDown.grid(row=(counter),column = 1)
                if (counter > 0): ## do not remove dataset [0]
                    buttonDelete = tk.Button(self.datadisplayframe,
                                        text='-',
                                        command=lambda i=counter:(self.deleteDataset(i)))
                    buttonDelete.grid(row=(counter),column = 2)

            ## add the currently stored data for the dataset
            tk.Label(self.datadisplayframe,width=3,text=counter).grid(row=(counter),column=3)
            tk.Label(self.datadisplayframe,width=6,text=thisdata[0]).grid(row=(counter),column=4)
            tk.Label(self.datadisplayframe,width=7,text=thisdata[1]).grid(row=(counter),column=5)
            tk.Label(self.datadisplayframe,width=7,text=thisdata[2]).grid(row=(counter),column=6)
            tk.Label(self.datadisplayframe,width=25,text=thisdata[3]).grid(row=(counter),column=7,sticky='ew')
            tk.Label(self.datadisplayframe,width=6,text=thisdata[4]).grid(row=(counter),column=8)

        self.update_data_layout()

    ## reorder the datasets, move current dataset one up
    def moveDatasetUp(self,current_position):
        i = current_position
        data.datasets[i], data.datasets[(i-1)] = data.datasets[(i-1)], data.datasets[i]
        self.displayDatasets()

    ## reorder the datasets, move current dataset one down
    def moveDatasetDown(self,current_position):
        i = current_position
        data.datasets[i], data.datasets[(i+1)] = data.datasets[(i+1)], data.datasets[i]
        self.displayDatasets()

    ## reorder the datasets, delete the current dataset
    def deleteDataset(self,current_position):
        i = current_position
        del data.datasets[i]
        self.displayDatasets()

    def displayCommSettings(self):
        self.current_ipaddress = tk.Label(self.settingsframe, text=data.ipaddress, bg='white')
        self.current_ipaddress.grid (row=2,column=1,sticky='EW')
        self.input_ipaddress = tk.Entry(self.settingsframe, width=15, fg='blue')
        self.input_ipaddress.grid(row=2,column=2, sticky = 'W') # needs to be on a separate line for variable to work
        self.input_ipaddress.bind('<Return>',self.updateCommSettings) ## enable the Entry to update without button click

        self.current_portno = tk.Label(self.settingsframe, text=data.portno, bg='white')
        self.current_portno.grid (row=3,column=1,sticky='EW')
        self.input_portno = tk.Entry(self.settingsframe, width=5, fg='blue')
        self.input_portno.grid(row=3,column=2, sticky = 'W')
        self.input_portno.bind('<Return>',self.updateCommSettings) ## update without button click

        self.current_modbusid = tk.Label(self.settingsframe, text=data.modbusid, bg='white')
        self.current_modbusid.grid (row=4,column=1,sticky='EW')
        self.input_modbusid = tk.Entry(self.settingsframe, width=5, fg='blue')
        self.input_modbusid.grid(row=4,column=2, sticky = 'W')
        self.input_modbusid.bind('<Return>',self.updateCommSettings) ## update without button click

        self.current_manufacturer = tk.Label(self.settingsframe, text=data.manufacturer, bg='white')
        self.current_manufacturer.grid (row=5,column=1,sticky='EW')
        self.input_manufacturer = tk.Entry(self.settingsframe, width=25, fg='blue')
        self.input_manufacturer.grid(row=5,column=2, sticky = 'W')
        self.input_manufacturer.bind('<Return>',self.updateCommSettings) ## update without button click

        self.current_loginterval = tk.Label(self.settingsframe, text=data.loginterval, bg='white')
        self.current_loginterval.grid (row=6,column=1,sticky='EW')
        self.input_loginterval = tk.Entry(self.settingsframe, width=3, fg='blue')
        self.input_loginterval.grid(row=6,column=2, sticky = 'W')
        self.input_loginterval.bind('<Return>',self.updateCommSettings) ## update without button click

    ## function for updating communication parameters with input sanitation
    #  if no values are given in some fields the old values are preserved
    #
    def updateCommSettings(self,*args):

        #print('update Communication Settings:')
        if self.input_ipaddress.get() != '':
            thisipaddress = str(self.input_ipaddress.get())
            ## test if the data seems to be a valid IP address
            try:
                self.ip_address(thisipaddress)
                data.ipaddress = str(self.input_ipaddress.get())
            except:
                messagebox.showerror('IP Address Error','the data you entered seems not to be a correct IP address')
            ## if valid ip address entered store it

        if self.input_portno.get() != '':
            ## test if the portnumber seems to be a valid value
            try:
                check_portno = int(self.input_portno.get())
                if check_portno < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror('Port Number Error','the value you entered seems not to be a valid port number')
                return
            data.portno = int(self.input_portno.get())

        if self.input_modbusid.get() != '':
            ## test if the modbus ID seems to be a valid value
            try:
                check_modbusid = int(self.input_portno.get())
                if check_modbusid < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror('Port Number Error','the value you entered seems not to be a valid Modbus ID')
                return
            data.modbusid = int(self.input_modbusid.get())

        if self.input_manufacturer.get() != '':
            data.manufacturer = (self.input_manufacturer.get())

        if self.input_loginterval.get() != '':
            ## test if the logger intervall seems to be a valid value
            try:
                check_loginterval = int(self.input_loginterval.get())
                if check_loginterval < 1:
                    raise ValueError
            except ValueError:
                messagebox.showerror('Logger Interval Error','the value you entered seems not to be a valid logger interval')
                return
            data.loginterval = int(self.input_loginterval.get())

        self.displayCommSettings()

    ## function for starting communication and changing button function and text
    #
    def startCommunication(self):
        inout.runCommunication()
        self.commButton.configure(text='⏹ Stop Communication',bg='red', command=(self.stopCommunication))

    def stopCommunication(self):
        inout.stopCommunication()
        self.commButton.configure(text='▶ Start Communication',bg='lightblue', command=(self.startCommunication))

    ## function for reading configuration file
    #
    def selectImportFile(self):
        data.inifilename = filedialog.askopenfilename(title = 'Choose Configuration File',defaultextension='.ini',filetypes=[('Configuration file','*.ini'), ('All files','*.*')])

        ## update displayed filename in entry field
        self.input_inifilename.delete(0,tk.END)
        self.input_inifilename.insert(0,data.inifilename)

        self.displaySettings()

    ## function for checking for seemingly correct IP address input
    #
    def ip_address(self,address):
        valid = address.split('.')
        if len(valid) != 4:
            raise ValueError
        for element in valid:
            if not element.isdigit():
                raise ValueError
                break
            i = int(element)
            if i < 0 or i > 255:
                raise ValueError
        return

    ## function for selecting configuration export file
    #
    def selectExportFile(self):
        data.inifilename = filedialog.asksaveasfilename(initialfile = data.inifilename,
                                                  title = 'Choose Configuration File',
                                                  defaultextension='.ini',
                                                  filetypes=[('Configuration file','*.ini'), ('All files','*.*')])

        ## update displayed filename in entry field
        self.input_inifilename.delete(0,tk.END)
        self.input_inifilename.insert(0,data.inifilename)

        inout.writeExportFile()

    ## function for updating the current received data on display
    #
    def updateLoggerDisplay(self):
        thisdata = '' ## make variable data known
        ## delete old data
        for displayed in self.targetdataframe.winfo_children():
            displayed.destroy()
        ## display new data
        tk.Label(self.targetdataframe,text='Value').grid(row=0,column=0)
        for thisdata in data.datavector:
            ## send data to display table
            tk.Label(self.targetdataframe,text=thisdata,bg='white').grid(column=0,sticky='e')

    ## function for setting program preferences (if needed)
    #
    def dataSettings(self):
        print('dataSettings')

    ## function for updating the configuration file
    #   with the path entered into the text field
    #
    def getInputFile(self,event):
        data.inifilename = event.widget.get()

    ## function adds dataset to the datasets list
    #   also updates the displayed list
    #   new datasets are not added to the config file
    #
    def addNewDataset(self):
        inout.addDataset([self.input_modaddress.get(),
                          self.input_moddatatype.get(),
                          self.input_dataformat.get(),
                          self.input_description.get(),
                          self.input_dataunit.get()])
        self.displayDatasets()
        #print (data.datasets)

    ## function for displaying the about dialog
    #
    def aboutDialog(self):
        messagebox.showinfo('About Python Modbus Monitor'\
                 ,'This is a program that acts as a modbus slave to receive data from modbus masters like SMA solar inverters. \nYou can choose the data to be received via the GUI and see the live data. \nYou can also call the programm from the command line with a configuration file given for the data to be retrieved. \nThe configuration file can be generated using the GUI command \"File\"→\"Export Configuration\"')

    ## function for closing the program window
    #
    def closeWindow(self):
        exit()
#------------------------- GUI class ---------------------------------------------------------------

## create a data object
data = Data()

## create an input output object
inout = Inout()

## create led object
led = LED()

## create GLCD object
cglcd = CGLCD()
cglcd.init()

## create the canvas for data presentation
canvas = Canvas()

## what to do on program exit
atexit.register(inout.cleanOnExit)

## create main program window
## if we are in command line mode lets detect it
gui_active = 0
if (arguments['--nogui'] == False):
    ## load graphical interface library
    import tkinter as tk
    from tkinter import messagebox
    from tkinter import filedialog
    try: ## if the program was called from command line without parameters
        window = tk.Tk()
        ## create window container
        gui = Gui(window)
        gui_active = 1
        if (arguments['--inifile'] != None):
            inout.checkImportFile()
            gui.displaySettings()

        tk.mainloop()
        exit() ## if quitting from GUI do not proceed further down to command line handling
    except tk.TclError:
        ## check if one of the required command line parameters is set
        if ((arguments['--inifile'] == None) and (arguments['--ip'] == None)):
            print('Error. No graphical interface found. Try "python pymodmon.py -h" for help.')
            exit()
        ## else continue with command line execution

########     this section handles all command line logic    ##########################

## read the configuration file
if (arguments['--inifile'] != None):
    inout.checkImportFile()

## get log interval value and check for valid value
if (arguments['--loginterval'] != None):
    try:
        check_loginterval = int(arguments['--loginterval'])
        if check_loginterval < 1:
            raise ValueError
    except ValueError:
        print('Log interval error. The interval must be 1 or more.')
        exit()
    data.loginterval = int(arguments['--loginterval'])

## initialize LED and GLCD
led.display()
cglcd.init()

## activates backlight
led.set_led("backlight",1)
led.display()

if (arguments['--graphical'] != None):
    disp_graphical = 1
else:
    disp_graphical = 0

## start polling data
## single poll first
inout.runCommunication()
## if --single is set, exit immediately
if (arguments['--single'] == True):
    inout.stopCommunication()
    print('single run')
    exit()

