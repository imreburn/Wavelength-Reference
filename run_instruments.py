import sys
import pyvisa
import time
import numpy as np
# import pandas as pd
import logging

from prep_instruments import prep_inst
from structs import Params

log = logging.getLogger(__name__)

power_limit = {"10": 10e-3,
             "0"  : 1.9999e-3,
             "-10": 199.99e-6,
             "-20": 19.999e-6,
             "-30": 1.9999e-6,
             "-40": 199.99e-9,
             "-50": 19.999e-9,
             "-60": 1.9999e-9,
             "-70": 199.99e-12}

def run_sweep(pm, laser, params, dryrun=False):
    log.info(f"Type: {params.sweep_type}")
    log.info("--- Running instruments ---")
    
    tls_wl_start = params.wl_start - params.padding
    tls_wl_stop  = params.wl_stop  + params.padding

    # ----- Power Meter -----
    pm.write(":INIT1:CONT 0")
    pm.write(":SENS1:FUNC:STAT LOGG, STOP")
    pm.write(f":SENSE1:CHAN1:POW:WAVE {tls_wl_stop:.3f} NM")
    pm.write(f":SENSE1:CHAN1:POW:ATIME {params.at_us} US")
    pm.write(":SENSE1:CHAN1:CORR 0")
    pm.write(":SENSE1:CHAN1:POW:RANGE:AUTO  0")
    pm.write(f":SENSE1:CHAN1:POW:RANGE  {params.pm_range} DBM")
    pm.write(":SENSE1:CHAN1:POW:UNIT  1")   # W (faster)
    pm.write(":TRIG1:CHAN1:OUTP DIS")
    pm.write(":TRIG1:CHAN1:INP  CME")
    pm.write(":TRIG:CONF PASS")
    pm.write(f":SENSE1:CHAN1:FUNC:PAR:LOGG {params.num_data}, {params.at_us} US")

    # log.info(f"[PM] Power Range: {pm.query(":SENSE1:CHAN1:POW:RANGE?")}")

    # ----- Laser -----
        
    laser.write(f":SOURCE0:WAVE  {tls_wl_start:.3f} NM")
    
    time.sleep(0.1)
    if (w := (float(laser.query(":SOURCE0:WAVE?"))*1e9)) != tls_wl_start:
        log.warning(f"[LASER] The current wavelength: {w}. Laser is still being adjusted.")
        
    laser.write(":SOURCE0:POWER:UNIT  0")
    laser.write(f":SOURCE0:POWER {params.tls_dbm} DBM")
    laser.write(":SOURCE0:POW:STATE 1")
    laser.write(":TRIG:CONF LOOP")
    laser.write(":TRIG0:INP IGN")
    laser.write(":TRIG0:OUTP SWST")
    laser.write(":SOURCE0:WAV:SWE:LLOG OFF")
    laser.write(":SOURCE0:WAV:SWE:MODE CONT")
    laser.write(":SOURCE0:WAV:SWE:REP ONEW")
    laser.write(f":SOURCE0:WAV:SWE:SPE      {params.speed} NM/S")
    laser.write(f":SOURCE0:WAV:SWE:STAR     {tls_wl_start:.3f} NM")
    laser.write(f":SOURCE0:WAV:SWE:STOP     {tls_wl_stop:.3f} NM")

    laser_check_param = (laser.query(":SOUR0:WAV:SWE:CHEC?")).split(',')
    if int(laser_check_param[0]) != 0:
        log.error(f"[LASER] Failed parameter checks: {', '.join(laser_check_param)}")
    else:
        log.info("[LASER] Passed parameter checks")

    # Check system errors
    if (n := int(laser.query(":SYST:ERR:COUN?"))) > 0:
        for _ in range(n):
            log.error(f"[LASER] System error: {laser.query(':SYST:ERR?')}")
        sys.exit(1)
    
    pm_check_error1 = (pm.query(":SYST:ERR?")).split(',')
    if int(pm_check_error1[0]) != 0:
        while True:
            log.error("[PM] System error: ", *pm_check_error1)
            pm_check_error1 = (pm.query(":SYST:ERR?")).split(',')
            if int(pm_check_error1[0]) == 0:
                break
        sys.exit(1)

    if dryrun:
        return None
    
    # PM: arm logging function before sweep starts
    pm.write(":SENS1:FUNC:STAT LOGG, START")

    # TLS: starts continuous sweep
    laser.write(":SOURCE0:WAV:SWE:STATE 1")
    log.info("[LASER] Start a continuous sweep")

    # Hold execution until sweep finishes
    while int(laser.query(":SOURCE0:WAV:SWE:STATE?")) == 1:
        log.info("[LASER] Sweeping...")
        time.sleep(1)

    log.info("[LASER] Sweep finished")

    # PM: read logged data
    log.info("[PM] Read logged measurements")
    pm.write(":SENS1:FUNC:RES?")
    time.sleep(2)
    arr_w = pm.read_binary_values(container=np.ndarray)
    
    log.info(f"[PM] Log count: {len(arr_w)}")
    
    pm.write(":SENS1:FUNC:STAT LOGG, STOP")
    
    # TLS will stay at the stop wavelength after a sweep
    laser.write(f":SOURCE0:WAVE  {params.wl_stop:.3f} NM")

    upper_limit = power_limit[str(params.pm_range)]
    arr_w[arr_w > upper_limit] = np.nan    
    if np.all(np.isnan(arr_w)):
        log.error("All measurements are overflown.")
    elif np.any(np.isnan(arr_w)):
        log.warning("There are some overflown measurements.")
        
    arr_dbm  = 10 * np.log10(arr_w.astype(np.float64) / 1e-3)  # convert: W -> dBm
    arr_dbm *= -1                                              # power loss 
    
    # Generate x-axis
    wav_stop_tmp = tls_wl_start + (params.step_pm * 1e-3) * (params.num_data - 1)
    wav_range    = np.linspace(tls_wl_start, wav_stop_tmp, params.num_data).round(7)

    i_lo = np.searchsorted(wav_range, params.wl_start - params.step_pm * 1e-3, side='left')
    i_hi = np.searchsorted(wav_range, params.wl_stop  + params.step_pm * 1e-3, side='right')
    
    return (wav_range[i_lo:i_hi], arr_dbm[i_lo:i_hi])

if __name__ == "__main__":
    pm, laser = prep_inst()