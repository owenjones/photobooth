#!/usr/bin/python3
#
# A crappy photobooth, using PiCamera and gpiozero
# Questions etc. - Owen Jones (owen@owenjones.net)
#
# Known Bugs :
#   * Ctrl+c exiting is broken
#
# Improvements :
#   * Show picture after it's taken
#   * Make output reliable somehow
#

from pathlib import Path
from threading import Timer
from time import sleep
from datetime import datetime

from picamera import PiCamera
from gpiozero import Button as GPIOButton
from PIL import Image

UPLOAD = Path("/home/photobooth/photos")
OVERLAYS = Path("/home/photobooth/booth/overlays/")
TRIGGER = 6  # Button GPIO Pin (Broadcom Numbering)
TIMEOUT = 300  # Seconds before going to sleep


class Photobooth:
    # Global States
    isCapturing = False
    isWaiting = False
    isReady = False
    isAtomic = False
    isClosing = False
    isSleeping = False

    # Global Timers
    sleepT = None

    # Shared Objects
    overlay1 = None
    overlay2 = None
    camera = None
    button = None

    # ==== Overlay Handlers ====
    def newOverlay(self, i, l=0, a=255):
        img = Image.open(OVERLAYS / "{}.bmp".format(i)).tobytes()
        ov = self.camera.add_overlay(img, size=self.camera.resolution, layer=l, alpha=a)
        return ov

    def updateOverlay(self, ov, i, l):
        img = Image.open(OVERLAYS / "{}.bmp".format(i)).tobytes()
        ov.update(img)
        ov.layer = l
        return ov

    def showOverlay(self, ov):
        ov.layer = 4

    def hideOverlay(self, ov):
        ov.layer = 1

    # ==== State Transitions ====
    def wakepress(self):
        self.isWaiting = False

    def capturepress(self):
        self.isCapturing = True

    def sleep(self):
        self.isSleeping = True

    ## ==== Setup ====
    def __init__(self):
        print("Photobooth initialising...")
        self.camera = PiCamera()
        self.camera.resolution = (1920, 1080)
        self.camera.rotation = 180
        self.camera.hflip = True
        self.button = GPIOButton(TRIGGER, pull_up=True, hold_time=10)
        self.overlay1 = self.newOverlay("splash", 4)

    def start(self):
        self.camera.start_preview()
        self.isReady = True
        self.wait()  # Wait for something to happen...

    def stop(self):
        self.clearTimer()

        self.isClosing = True
        self.isReady = False
        self.isWaiting = False
        self.isCapturing = False
        self.isSleeping = False

        if self.button:
            self.button.when_pressed = None

        if self.camera:
            # if self.overlay1 : self.camera.remove_overlay(self.overlay1)
            # if self.overlay2 : self.camera.remove_overlay(self.overlay2)
            self.camera.stop_preview()
            self.camera.close()

        print("Photobooth exiting...")
        exit()

    # ==== States ====
    def clearTimer(self):
        if self.sleepT:
            self.sleepT.cancel()
            # self.sleepT = None

    def wait(self):
        # A sleep state at startup/when not being used
        if not self.isReady:
            return
        self.clearTimer()

        self.overlay1.alpha = 255
        self.updateOverlay(self.overlay1, "splash", 3)

        self.isWaiting = True
        self.button.when_pressed = self.wakepress
        while self.isWaiting:
            sleep(0.05)  # Wait until woken
        if self.isClosing:
            return  # Catch a closing signal from behind the scenes
        self.button.when_pressed = None
        self.wakeup()

    def wakeup(self):
        # Transition from sleeping to main loop
        if not self.isReady:
            return
        self.isSleeping = False

        self.hideOverlay(self.overlay1)
        self.updateOverlay(self.overlay1, "2", 0)
        self.overlay1.alpha = 128

        sleep(0.5)  # Let video output settle and prevent double triggering
        self.loop()

    def loop(self):
        while self.isReady and not self.isWaiting:
            self.button.when_pressed = self.capturepress
            self.sleepT = Timer(TIMEOUT, self.sleep).start()
            while not self.isCapturing and not self.isSleeping:
                sleep(0.01)  # Wait here until the button is pressed or we go to sleep
            self.clearTimer()
            self.button_when_pressed = None
            if self.isClosing:
                return
            elif self.isSleeping:
                self.wait()
            else:
                self.capture()

    def capture(self):
        if not self.isReady:
            return
        if self.isAtomic:
            return  # For atomicity (prevents re-triggering whilst capture is in progress)
        self.isAtomic = True
        self.countdown()

        path = UPLOAD / "{}.jpg".format(datetime.now().strftime("%Y.%m.%d-%H.%M.%S"))
        self.camera.capture(bytes(path))
        sleep(1)  # Wait on "flash" screen for effect

        self.camera.start_preview()

        self.hideOverlay(self.overlay1)
        self.camera.remove_overlay(self.overlay2)
        self.updateOverlay(self.overlay1, "2", 1)
        self.overlay1.alpha = 128

        self.isAtomic = False
        self.isCapturing = False

    def countdown(self):
        if not self.isReady and not self.isCapturing:
            return
        # Working out the order of all these overlay transitions is a fine art...
        self.overlay2 = self.newOverlay("3", 4, 128)
        sleep(1)
        self.showOverlay(self.overlay1)
        self.hideOverlay(self.overlay2)
        self.updateOverlay(self.overlay2, "1", 1)
        sleep(1)
        self.showOverlay(self.overlay2)
        self.hideOverlay(self.overlay1)
        sleep(1)
        self.updateOverlay(self.overlay1, "flash", 4)
        self.overlay1.alpha = 255
        self.camera.stop_preview()
        self.hideOverlay(self.overlay2)


if __name__ == "__main__":
    pb = Photobooth()

    try:
        pb.start()
        # Do all the things
        pb.stop()

    except KeyboardInterrupt:
        pb.stop()
