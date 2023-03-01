#!/bin/python3
import ctypes
import numpy as np
import time
from libqhy import *

TYPE_CHAR20 = ctypes.c_char * 20
TYPE_CHAR32 = ctypes.c_char * 32

class QHYCCDSDK():
    '''Class interface for the QHYCCD SDK
    '''
    def __init__(self, dll_path='/usr/local/lib/libqhyccd.so'):
        '''
        '''
        # create sdk handle
        self._sdk = ctypes.CDLL(dll_path)

        self._sdk.GetQHYCCDParam.restype = ctypes.c_double
        self._sdk.OpenQHYCCD.restype = ctypes.POINTER(ctypes.c_uint32)
        
        ret = self._sdk.InitQHYCCDResource()

        self._number_of_cameras = self._sdk.ScanQHYCCD()
        
        self._camera_handles = {}
        self._ids = []
        
    def __del__(self):
        '''
        '''
        # Go through all camera handles and close the ones that are open
        for cam_handle in self._camera_handles:
            self._sdk.CloseQHYCCD(cam_handle)
            
        self._sdk.ReleaseQHYCCDResource()
    
    def list_cameras(self):
        '''
        '''
        for i in range(self._number_of_cameras):
            self.ids.append( TYPE_CHAR32() )
            self.sdk.GetQHYCCDId(ctypes.c_int(i), self.ids[-1])
            print("Cameras {:d} ID {:s}".format(i, self.ids[-1].value))
            
    def open_camera(self, camera_id):
        '''
        '''
        if camera_id in self._camera_handles:
            return self._camera_handles[camera_id]
        else:
            # Open connection to the camera and initialize its resources
            self._camera_handles[camera_id] = self._sdk.OpenQHYCCD(self._ids[camera_id])
            self._sdk.InitQHYCCD(self._camera_handles[camera_id])
            
            return self._camera_handles[camera_id]
    
    def close_camera(self, camera_id):
        '''
        '''
        if camera_id in self._camera_handles:
            # Close connection to camera
            self._sdk.CloseQHYCCD(self._camera_handles[camera_id])
            
            # Remove camera from active list
            del self._camera_handles[camera_id]
    
    #def get_camera_properties(self, camera_handle):
    #    GetQHYCCDModel(TYPE_CHAR20)
        
    def get_parameter_limits(self, camera_handle, parameter):
        param_min = ctypes.c_double
        param_max = ctypes.c_double
        param_step = ctypes.c_double
        
        self._sdk.GetQHYCCDParamMinMaxStep(camera_handle, parameter, ctypes.byref(param_min), ctypes.byref(param_max), ctypes.byref(param_step))
        
        return param_min.value, param_max.value, param_step.value
    
    def get_all_limits(self, camera_handle):
        min_gain, max_gain, step_gain = self.get_parameter_limits(camera_handle, CONTROL_ID.CONTROL_GAIN)
        min_exp, max_exp, step_exp = self.get_parameter_limits(camera_handle, CONTROL_ID.CONTROL_EXPOSURE)
        
        parameter_limits = {
            'exp' : [min_exp, max_exp, step_exp],
            'gain' : [min_gain, max_gain, step_gain]
        }
        
        return parameter_limits
    
    def get_chip_info(self, camera_handle):
        # Get Camera Parameters
        chip_width = ctypes.c_double()
        chip_height = ctypes.c_double()
        width = ctypes.c_uint()
        height = ctypes.c_uint()
        pixel_width = ctypes.c_double()
        pixel_height = ctypes.c_double() 
        channels = ctypes.c_uint32(1)
        bpp = ctypes.c_uint()
        
        self._sdk.GetQHYCCDChipInfo(camera_handle, ctypes.byref(chip_width), ctypes.byref(chip_height), ctypes.byref(width), ctypes.byref(height), ctypes.byref(pixel_width), ctypes.byref(pixel_height), ctypes.byref(bpp))
        
        chip_info = {
            'physical' : [chip_width.value, chip_height.value],
            'size' : [width.value, height.value],
            'pixel_size' : [pixel_width.value, pixel_height.value],
            'channels' : channels.value,
            'bpp' : bpp.value
        }
        
        return chip_info
        
    
    @property
    def number_of_cameras(self):
        return self._number_of_cameras
        
    @property
    def version(self):
        year = ctypes.c_uint32()
        month = ctypes.c_uint32()
        day = ctypes.c_uint32()
        subday = ctypes.c_uint32()
        
        # Year starts counting at 2000 so we add 2000 to the returned value
        ret = self._sdk.GetQHYCCDSDKVersion(ctypes.byref(year), ctypes.byref(month), ctypes.byref(day), ctypes.byref(subday))
        return '{:d}-{:>02d}-{:>02d}'.format(2000 + year.value, month.value, day.value)
    
    def set_parameter(self, camera_handle, parameter, value):
        self._sdk.SetQHYCCDParam(camera_handle, parameter, value)
    
    def get_parameter(self, camera_handle, parameter):
        return self._sdk.GetQHYCCDParam(self.cam, CONTROL_ID.CONTROL_EXPOSURE)

class QHYCCDCamera():
    ''' A class that interface with the QHYCCD series of cameras.
    '''
    def __init__(self, sdk, camera_id, new_bpp=16):
        # create sdk handle
        self._sdk = sdk
        self._camera = self._sdk.open_camera(camera_id)
        
        self._stream_mode = 0 # set default mode to stream mode, otherwise set 0 for single frame mode
        
        self.bpp(new_bpp)
        self.exposure_time(100.0)
        self.gain(1.0)
                
        # Get Camera Parameters
        self._chip_info = self._sdk.get_chip_info(self._camera)
        self._width = self._chip_info['size'][0]
        self._height = self._chip_info['size'][1]
        
        # Always cool to zero at startup.
        self.target_temperature(0.0)
        
        # Set ROI and readout parameters
        self._set_roi(0, 0, self._width, self._height)
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_USBTRAFFIC, ctypes.c_double(50))
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_TRANSFERBIT, ctypes.c_double(self._bpp))

    def cancel_exposure(self):
        pass
        
    @property
    def temperature(self):
        self._temperature = self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_CURTEMP)
        return self._temperature
    
    @property
    def target_temperature(self):
        return self._target_temperature
        
    @target_temperature.setter
    def target_temperature(self, new_temperature):
        self._target_temperature = new_temperature
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_COOLER, ctypes.c_double(self._target_temperature))
    
    @property
    def exposure_time(self):
        return self._exposure_time
    
    @exposure_time.setter
    def exposure_time(self, new_exposure_time):
        # QHYCCD SDK uses microseconds as unit
        # The QHYCCD VIS-X interface uses seconds as the unit. Carefull with converting units!
        self._exposure_time = new_exposure_time
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_EXPOSURE, ctypes.c_double(self._exposure_time * 1e6))
        print("Set exposure time to", self._sdk.get_parameter(self._camera, CONTROL_ID.CONTROL_EXPOSURE) / 1e6)
    
    @property
    def gain(self):
        return self._gain
    
    @gain.setter
    def gain(self, new_gain):
        self._gain = new_gain
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_GAIN, ctypes.c_double(self._gain))
    
    #""" Set camera depth """
    @property
    def bpp(self):
        return self._bpp
    
    @bpp.setter
    def bpp(self, new_bpp):
        self._bpp = new_bpp
        self._sdk.set_parameter(self._camera, CONTROL_ID.CONTROL_TRANSFERBIT, ctypes.c_double(self._bpp))

    #""" Set camera ROI """
    def set_roi(self, x0, y0, roi_w, roi_h):
        # update the image buffer
        if self._bpp == 16:
            self._imgdata = (ctypes.c_uint16 * roi_w * roi_h)()
            self._sdk._sdk.SetQHYCCDResolution(self.cam, ctypes.c_unint(x0), ctypes.c_unint(y0), ctypes.c_uint(roi_w), ctypes.c_uint(roi_h))
        else: # 8 bit
            self._imgdata = (ctypes.c_uint8 * roi_w * roi_h)()
            self._sdk._sdk.SetQHYCCDResolution(self.cam, ctypes.c_unint(x0), ctypes.c_unint(y0), ctypes.c_uint(roi_w), ctypes.c_uint(roi_h))

    def start_exposure(self):
        ret = self._sdk.sdk.ExpQHYCCDSingleFrame(self._camera)
        
    def remaining_time(self):
        percentage_complete = self._sdk.sdk.GetQHYCCDExposureRemaining(self._camera) # This counts the completion rate in percentages
        remaining = (100.0 - percentage_complete)/100.0 * self.exposure_time
        return remaining
    
    def is_exposure_finished(self):
        if self.remaining_time < 1.0:
            return True
        else:
            return False
    
    def readout(self):
        ret = self._sdk.sdk.GetQHYCCDSingleFrame(self._camera, ctypes.byref(self._roi_w), ctypes.byref(self._roi_h), ctypes.byref(self._bpp), ctypes.byref(self._channels), self._imgdata)
        return np.asarray(self._imgdata)
    
    def get_singleframe(self):
        ret = self._sdk.sdk.ExpQHYCCDSingleFrame(self._camera)
        ret = self._sdk.sdk.GetQHYCCDSingleFrame(self._camera, ctypes.byref(self._roi_w), ctypes.byref(self._roi_h), ctypes.byref(self._bpp), ctypes.byref(self._channels), self._imgdata)
        return np.asarray(self._imgdata)
