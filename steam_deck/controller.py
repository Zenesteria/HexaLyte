import sys
import os, struct, array
import logging
import time
import queue
from fcntl import ioctl
import threading
from spec.ttypes import ButtonID, AxisID
from spec.ARR_proto import Client
from typing import List


logger = logging.getLogger(__name__)


class SteamDeckController:

    dev_loc = "/dev/input/"

    axis_map = [
        AxisID.LX,
        AxisID.LY,
        AxisID.THROTTLE_L,
        AxisID.RX,
        AxisID.RY,
        AxisID.THROTTLE_R,
        AxisID.PAD_X,
        AxisID.PAD_Y
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

    def __init__(self, thrift_client: Client, collect_logs= False) -> None:
        self.fn: str = self.await_controller()

        logger.info("Connecting to controller")
        self.jsdev = open(self.fn, 'rb')

        buf = array.array('B', [0] * 64)
        ioctl(self.jsdev, 0x80006a13 + (0x10000 * len(buf)), buf)
        self.js_name = buf.tobytes().rstrip(b'\x00').decode('utf-8')
        logger.info('Device name: %s', self.js_name)

        self.collect_logs = collect_logs
        self.log_queue = queue.Queue()
        self.current_state = {
            "axises": {},
            "buttons": {},
        }
        self.previous_state = {
            "axises": {},
            "buttons": {},
        }
        self.monitor_thread = threading.Thread(target=self._monitor_dev)
        self.thrift_client = thrift_client
        self.monitor_dev()
        
        


    def await_controller(self) -> str:
        logger.info("Waiting for controller")
        while True:
            for fn in os.listdir(self.dev_loc):
                if fn.startswith('js'):
                    logger.info( 'Controller found: %s%s', self.dev_loc, fn)
                    return f"{self.dev_loc}{fn}"
                else:
                    logger.warning("Controller not found")
                    time.sleep(1)


    def monitor_dev(self) -> None:
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
                    self.current_state["buttons"][self.button_map[number]] = value

                elif type & 0x02:
                    if number != 6 and number != 7:
                        self.current_state["axises"][self.axis_map[number]] = value
                        logger.debug("%s: %.3f" % (self.axis_map[number], value))
                    elif number == 6 and value == -32767:
                        # self.current_state["buttons"][] = 
                        self.current_state["buttons"][ButtonID.PAD_LEFT] = 1 
                    elif number == 6 and value == 32767:
                        self.current_state["buttons"][ButtonID.PAD_RIGHT] = 1
                    elif number ==6 and value == 0:
                        self.current_state["buttons"][ButtonID.PAD_LEFT] = 0
                        self.current_state["buttons"][ButtonID.PAD_RIGHT] = 0
                    elif number == 7 and value == -32767:
                        self.current_state["buttons"][ButtonID.PAD_UP] = 1
                    elif number == 7 and value == 32767:
                        self.current_state["buttons"][ButtonID.PAD_DOWN] = 1
                    elif number == 7 and value == 0:
                        self.current_state["buttons"][ButtonID.PAD_UP] = 0
                        self.current_state["buttons"][ButtonID.PAD_DOWN] = 0

    def send_update(self):
        self.current_state_copy = self.current_state.copy()
        for button_id, value in self.current_state_copy.get("buttons").items():
            if value != self.previous_state.get("buttons").get(button_id, 0):
                self.thrift_client.button(button_id, value)
        for axis_id, value in self.current_state_copy.get("axises").items():
            if value != self.previous_state.get("axises").get(axis_id, 0):
                self.thrift_client.axis(axis_id, value)
        
        self.previous_state["buttons"] = self.current_state_copy.get("buttons").copy()
        self.previous_state["axises"] = self.current_state_copy.get("axises").copy()

        if self.collect_logs:
            for line in self.thrift_client.get_logs(0):
                self.log_queue.put(line)


    def terminate(self) -> None:
        self._terminate_monitor = True
        self.monitor_thread.join()
        self.thrift_client = None
        return