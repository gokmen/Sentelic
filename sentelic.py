#!/usr/bin/python
#-*- coding: utf-8 -*-

#  Sentelic Mouse (Asus UX31) disable daemon while typing.
#  Copyright (C) 2011 Gökmen Göksel <gokmen@goksel.me>
#
#  X Key event capture code inherited from pyxhook example of Tim Alexander
#  Copyright (C) 2008 Tim Alexander <dragonfyre13@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This requires:
#  at least python-xlib 1.4
#  xwindows must have the "record" extension present, and active.

import os
import sys
import time
import signal
import threading

from Xlib import X, display
from Xlib.ext import record
from Xlib.protocol import rq

# Example content for /etc/sentelic.conf
#
# device=/path_to/device
# timeout=1.5

# If config file is empty it tries to find correct device from dmesg output
# and uses 0.9 as default timeout

# Read config value if exists
def getConfigValue(key):
    if os.path.exists('/etc/sentelic.conf'):
        for line in open('/etc/sentelic.conf', 'r').readlines():
            if line.startswith(key):
                return line.split('=')[1].strip()
    return None

# Find proper device to control
# Sentelic Mouse touch to click handler class
class SentelicHandler:

    def __init__(self):
        #Try to get the Sentelic touchpad device path from udev, fallback to
        #hardcoded one
        try:
            from pyudev import Context
            ctx = Context()

            for dev in ctx.list_devices(subsystem='input', ID_INPUT_MOUSE=True):
                if dev.sys_name.startswith('input'):
                    SYS_PATH = dev.sys_path.split('input')[0]
        except ImportError:
            SYS_PATH = "/sys/devices/platform/i8042/serio4"

        self.REG_FILE = os.path.join(SYS_PATH, 'setreg')
        self.STATE_FILE = os.path.join(SYS_PATH, 'flags')
        print "Info: Sentelic device found at %s " % SYS_PATH

        self.__enable_register()
        self.state = False
        self.setState(True, True)

    def __enable_register(self):
        try:
            open(self.REG_FILE, 'w').write('0x90 0x80')
        except:
            print "Error: Failed to update register file at %s" % self.REG_FILE
            sys.exit(1)

    def setState(self, state, force = False):
        if not state == self.state or force:
            try:
                open(self.STATE_FILE, 'w').write({True:'C', False:'c'}[state])
                self.state = state
            except:
                print "Error: Failed to update state at %s" % self.STATE_FILE
                sys.exit(1)

    def disable(self):
        self.setState(False)

    def enable(self):
        self.setState(True)

# X Key event threaded class
class XKeyEventThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

        self.finished = threading.Event()
        self.timer = None
        self.contextEventMask = [X.KeyPress,X.MotionNotify]

        self.local_dpy = display.Display()
        self.record_dpy = display.Display()

        self.siktelic = SentelicHandler()
        self.timeout = getConfigValue('timeout') or 0.9

    def killTimer(self):
        if self.timer:
            if self.timer.isAlive():
                self.timer.cancel()
        self.siktelic.disable()

    def fireTimer(self):
        if self.timer:
            if self.timer.isAlive():
                self.timer.cancel()
        self.timer = threading.Timer(float(self.timeout), self.siktelic.enable)
        self.timer.start()

    def run(self):
        if not self.record_dpy.has_extension("RECORD"):
            print "Error: RECORD extension not found"
            sys.exit(1)
        self.ctx = self.record_dpy.record_create_context(
                0,
                [record.AllClients],
                [{
                        'core_requests': (0, 0),
                        'core_replies': (0, 0),
                        'ext_requests': (0, 0, 0, 0),
                        'ext_replies': (0, 0, 0, 0),
                        'delivered_events': (0, 0),
                        'device_events': tuple(self.contextEventMask),
                        'errors': (0, 0),
                        'client_started': False,
                        'client_died': False,
                }])

        self.record_dpy.record_enable_context(self.ctx, self.processevents)
        self.record_dpy.record_free_context(self.ctx)

    def cancel(self):
        self.finished.set()
        self.local_dpy.record_disable_context(self.ctx)
        self.local_dpy.flush()

    def processevents(self, reply):
        if reply.category != record.FromServer:
            return
        if reply.client_swapped:
            return
        if not len(reply.data) or ord(reply.data[0]) < 2:
            return
        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, \
                    self.record_dpy.display, None, None)
            if event.type == X.KeyPress:
                self.killTimer()
            elif event.type == X.KeyRelease:
                self.fireTimer()

if __name__ == '__main__':

    if os.geteuid():
        print "You have to run the script as root!"
        os._exit(1)

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError, error:
        print 'Unable to fork. Error: %d (%s)' % (error.errno, error.strerror)
        os._exit(1)

    KeyEventGrabber = XKeyEventThread()
    KeyEventGrabber.start()
    print "Started to running..."

