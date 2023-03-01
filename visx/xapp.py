import numpy as np
import os
from purepyindi2 import device, properties, constants
from purepyindi2.messages import DefNumber, DefSwitch, DefText, DefLight
import ImageStreamIOWrap as ISIO
import logging
import time
import sys
log = logging.getLogger(__name__)

class VisX(device.XDevice):
    data_directory : str = "/opt/MagAOX/rawimages/camvisx"
    exposure_start_ts : float = 0
    exposure_time_sec : float = 0
    should_cancel : bool = False
    currently_exposing : bool = False
    should_begin_exposure : bool = False
    temp_controller_active : bool = False
    temp_target_deg_c : float = 0.0
    camera : object
    shmim : ISIO.Image
    frame : np.ndarray

    def handle_exptime(self, existing_property, new_message):
        if not self.currently_exposing and 'target' in new_message and new_message['target'] != existing_property['current']:
            existing_property['current'] = new_message['target']
            existing_property['target'] = new_message['target']
            self.exposure_time_sec = new_message['target']
            log.debug(f"Exposure time changed to {new_message['target']} seconds")
        if self.currently_exposing:
            log.debug("Ignoring exposure time change request while currently exposing")
        self.update_property(existing_property)
    
    def handle_expose(self, existing_property, new_message):
        if 'request' in new_message and new_message['request'] is constants.SwitchState.ON:
            log.debug("Exposure requested!")
            self.should_begin_exposure = True
        if 'cancel' in new_message and new_message['cancel'] is constants.SwitchState.ON:
            log.debug("Exposure cancellation requested")
            self.should_cancel = True
        self.update_property(existing_property)  # ensure the switch turns back off at the client

    def handle_temp_ccd(self, existing_property, new_message):
        if 'target' in new_message and new_message['target'] != existing_property['current']:
            existing_property['current'] = new_message['target']
            existing_property['target'] = new_message['target']
            self.temp_target_deg_c = new_message['target']
            log.debug(f"CCD temperature setpoint changed to {self.temp_target_deg_c} deg C")
        self.update_property(existing_property)

    def handle_temp_controller_toggle(self, existing_property, new_message):
        if 'toggle' not in new_message:
            return
        if self.properties['temp_ccd']['target'] is not None and new_message['toggle'] is constants.SwitchState.ON:
            self.temp_controller_active = True
            existing_property['toggle'] = constants.SwitchState.ON
        self.update_property(existing_property)

    def setup(self):
        os.makedirs(self.data_directory)
        detector_shape = (9600, 6422)
        self.shmim = ISIO.Image()
        if os.path.exists(f"/milk/shm/{self.name}.im.shm"):
            log.debug(f"Opening existing shmim for {self.name}")
            self.shmim.open(self.name)
            self.frame = self.shmim.copy()
        else:
            self.frame = np.zeros(detector_shape, dtype=np.uint16)
            self.shmim.create(
                self.name,
                self.frame,
            )
            log.debug(f"Created a shmim for {self.name}")
        log.debug(f"{self.frame.shape=} {self.frame.dtype=}")
        # Load SDK
        # sdk = load_sdk()
        # Find camera
        # self.camera = camera

        while self.client.status is not constants.ConnectionStatus.CONNECTED:
            log.info("Waiting for connection before trying to define properties...")
            time.sleep(1)
        sv = properties.SwitchVector(
            name='expose',
            rule=constants.SwitchRule.ONE_OF_MANY,
            perm=constants.PropertyPerm.READ_WRITE,
        )
        sv.add_element(DefSwitch(name="request", _value=constants.SwitchState.OFF))
        sv.add_element(DefSwitch(name="cancel", _value=constants.SwitchState.OFF))
        self.add_property(sv, callback=self.handle_expose)

        nv = properties.NumberVector(name='exptime', perm=constants.PropertyPerm.READ_WRITE)
        nv.add_element(DefNumber(
            name='current', label='Exposure time (sec)', format='%3.1f',
            min=0, max=1_000_000, step=1, _value=0.0
        ))
        nv.add_element(DefNumber(
            name='target', label='Requested exposure time (sec)', format='%3.1f',
            min=0, max=1_000_000, step=1, _value=0.0
        ))
        self.add_property(nv, callback=self.handle_exptime)

        nv = properties.NumberVector(name='temp_ccd', perm=constants.PropertyPerm.READ_WRITE)
        nv.add_element(DefNumber(
            name='current', label='Current temperature (deg C)', format='%3.3f',
            min=-100, max=100, step=0.1, _value=None
        ))
        nv.add_element(DefNumber(
            name='target', label='Requested temperature (deg C)', format='%3.3f',
            min=-100, max=100, step=0.1, _value=None
        ))
        self.add_property(nv, callback=self.handle_temp_ccd)

        sv = properties.SwitchVector(
            name='temp_controller',
            rule=constants.SwitchRule.ONE_OF_MANY,
            perm=constants.PropertyPerm.READ_WRITE,
        )
        sv.add_element(DefSwitch(name="toggle", _value=constants.SwitchState.OFF))
        self.add_property(sv, callback=self.handle_temp_controller_toggle)

        nv = properties.NumberVector(name='current_exposure')
        nv.add_element(DefNumber(
            name='remaining_sec', label='Time remaining (sec)', format='%3.1f',
            min=0, max=1_000_000, step=1, _value=0.0
        ))
        nv.add_element(DefNumber(
            name='remaining_pct', label='Percentage remaining', format='%i',
            min=0, max=100, step=0.1, _value=0.0
        ))
        self.add_property(nv)
        log.debug("Set up complete")

    def update_readonly_properties(self):
        now = time.time()
        current = self.properties['current_exposure']
        if self.currently_exposing:
            remaining_sec = max((self.exposure_start_ts + self.exposure_time_sec) - now, 0)
            remaining_pct = 100 * remaining_sec / self.exposure_time_sec
            log.debug(f"")
        else:
            remaining_sec = 0
            remaining_pct = 0
        if remaining_sec != current['remaining_sec']:
            current['remaining_sec'] = remaining_sec
            current['remaining_pct'] = remaining_pct
            self.update_property(current)


    def maintain_temperature_control(self):
        pass

    def begin_exposure(self):
        self.currently_exposing = True
        self.should_begin_exposure = False
        self.exposure_start_ts = time.time()
        #actually begin
        log.debug("Asking camera to begin exposure")

    def finalize_exposure(self, actual_exptime_sec=None):
        # Create FITS structure
        # Populate headers
        # Note if exposure was canceled
        # Write to /data path
        # Pass updated frame to shmim
        self.shmim.write(np.asfortranarray(self.frame))

    def cancel_exposure(self):
        self.currently_exposing = False
        self.should_cancel = False
        log.debug("Asking camera to cancel exposure")
        # actually cancel
        actual_exptime_sec = time.time() - self.exposure_start_ts
        self.finalize_exposure(actual_exptime_sec=actual_exptime_sec)

    def loop(self):
        now = time.time()
        if self.should_cancel:
            self.cancel_exposure()
        elif not self.currently_exposing and self.should_begin_exposure:
            self.begin_exposure()
        elif self.currently_exposing and now > (self.exposure_time_sec + self.exposure_start_ts):
            self.currently_exposing = False
            log.debug("Exposure finished")
            self.finalize_exposure()
        self.update_readonly_properties()
        self.maintain_temperature_control()

def main():
    if '-v' in sys.argv:
        logging.basicConfig(level=logging.INFO)
        log.setLevel(logging.DEBUG)
    app = VisX(name="camvisx")
    app.main()