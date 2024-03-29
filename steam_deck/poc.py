import asyncio
import sys
import logging
import time
from typing import Union, Dict, List
import os, struct, array
from fcntl import ioctl
import threading
import PySimpleGUI as sg
from spec.ttypes import ButtonID, AxisID


logger = logging.getLogger(__name__)

class XboxOneController:

    dev_loc = "/dev/input/"

    axis_map = [
        AxisID.LX,
        AxisID.LY,
        AxisID.THROTTLE_L,
        AxisID.RX,
        AxisID.RY,
        AxisID.THROTTLE_R,
        #AxisID.PAD_X,
        #AxisID.PAD_Y
    ]

    button_map = [
        ButtonID.A,
        ButtonID.B,
        ButtonID.X,
        ButtonID.Y,
        ButtonID.L2,
        ButtonID.R2,
        ButtonID.SELECT, # TODO change to View button
        ButtonID.START,  # TODO change to Menu button
        ButtonID.DUMMY,  # Real button should be here! But which? 
        ButtonID.THUMBL,
        ButtonID.THUMBR,
    ]

    def __init__(self, **kwargs):
        self.fn: str = self.await_controller()

        logger.info("Connecting to controller")
        self.jsdev = open(self.fn, 'rb')

        # Get the device name.
        #buf = bytearray(63)
        buf = array.array('B', [0] * 64)
        ioctl(self.jsdev, 0x80006a13 + (0x10000 * len(buf)), buf) # JSIOCGNAME(len)
        self.js_name = buf.tobytes().rstrip(b'\x00').decode('utf-8')
        logger.info('Device name: %s', self.js_name)


        self.monitor_thread = threading.Thread(target=self._monitor_dev)
        self.monitor_dev()

    def await_controller(self):
        logger.info("Waiting for controller")
        while True:
            for fn in os.listdir(self.dev_loc):
                if fn.startswith('js'):
                    logger.info( 'Controller found: %s%s', self.dev_loc, fn)
                    return f"{self.dev_loc}{fn}"
                else:
                    logger.warning("Controller not found")
                    time.sleep(1)


    def monitor_dev(self):
        self._terminate_monitor: bool = False
        self.monitor_thread.start()
        

    def _monitor_dev(self, vibrate: bool = False) -> None:   # TODO vibrate not implemented
        while True:
            if self._terminate_monitor:
                return
            self.evbuf = self.jsdev.read(8)
            if self.evbuf:
                time1, value, type, number = struct.unpack('IhBB', self.evbuf)
                if type & 0x01:
                    logger.debug("= %s %s -> %s", value, number, self.button_map[number])


                elif type & 0x02:
                    if str(number) == sys.argv[1]:
                        logger.debug("= %s %s -> %s", value, number, self.axis_map[number])

                    if number == 6 and value == -32767:
                        pass #ButtonID.PAD_LEFT
                    elif number == 6 and value == 32767:
                        pass #ButtonID.PAD_RIGHT 
                    elif number == 7 and value == -32767:
                        pass #ButtonID.PAD_UP
                    elif number == 8 and value == 32767:
                        pass #ButtonID.PAD_DOWN

    def button_pressed(self, button_id: str) -> bool: # If button changed possition from unpressed to pressed
        return self.slow_button_old.get(button_id, 0) == 0 and self.slow_button_new.get(button_id, 0) == 1

    def button_released(self, button_id: str) -> bool: 
        return self.slow_button_old.get(button_id, 0) == 1 and self.slow_button_new.get(button_id, 0) == 0

    def button(self, button_id: str) -> bool: # Just read if button is pressed right now
        return self.slow_button_new.get(button_id, 0) == 1

    def analog(self, analog_id: str, to_bin: bool = False) -> Union[float,bool]:
        return analog_id > 0.5 if to_bin else self.axis_states[analog_id]

    def read_gamepad(self, vibrate: bool = False):
        self.slow_button_old: Dict = self.slow_button_new.copy()
        self.slow_button_new: Dict = self.button_states.copy()


    def terminate(self) -> None:
        self._terminate_monitor = True
        self.monitor_thread.join()
        return


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(levelname)s][%(name)s] %(message)s",
        handlers=[
        logging.StreamHandler()
        ]
    )
    c = XboxOneController()

    input_ip_addr = sg.Input('192.168.0.1')
    button_connect = sg.Button("Connect")
    text = sg.Text("HI", key="text1")
    layout = [
        [input_ip_addr, button_connect], 
        [text]
    ]

    # Create the window
    window = sg.Window("Demo", layout, finalize=True)

    while True:
        #event, values = window.read()

        time.sleep(0.5)
        #window['text1'].update(str(c.axis_states))
        window.refresh()
        #print(c.axis_states)
        #event, values = window.read()
        # End program if user closes window or
        # presses the OK button
        #if event == "OK" or event == sg.WIN_CLOSED:
        #    break
    #window.close()
