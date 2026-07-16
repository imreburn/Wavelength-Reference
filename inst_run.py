import sys
import pyvisa
import time
import numpy as np
import logging

from inst_helper import prep_inst, check_inst
from constants import POWER_LIMIT
from structs import Params

log = logging.getLogger(__name__)


def run_sweep(pm, laser, params: Params, dryrun=False):
    """
    Returns a list of np 1-d arrays with the order matching with param.channel. (e.g. [Ch.1, Ch.2, Ch.3, Ch.4])
    """
    log.info("--- Running instruments ---") 
    
    check_inst(pm, laser)

    tls_wl_start = params.wl_start - params.padding
    tls_wl_stop  = params.wl_stop  + params.padding

    # ----- Power Meter -----
    for i in params.channel:
        pm.write(f":INIT{i}:CONT 0")
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, STOP")
        pm.write(f":SENSE{i}:POW:WAVE {tls_wl_stop:.3f} NM")
        pm.write(f":SENSE{i}:POW:ATIME {params.at_us} US")
        pm.write(f":SENSE{i}:CORR 0")
        pm.write(f":SENSE{i}:POW:RANGE:AUTO  0")
        pm.write(f":SENSE{i}:POW:RANGE  {params.pm_range} DBM")
        pm.write(f":SENSE{i}:POW:UNIT  1")   # W (faster)
        pm.write(f":TRIG{i}:OUTP DIS")
        pm.write(f":TRIG{i}:INP  CME")
        
        pm.write(f":SENSE{i}:FUNC:PAR:LOGG {params.num_data}, {params.at_us} US")
        # PM: arm logging function before sweep starts
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, START")

    pm.write(f":TRIG:CONF PASS")

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

    # ----- Laser: check parameter errors -----
    laser_check_param = (laser.query(":SOUR0:WAV:SWE:CHEC?")).split(',')
    if int(laser_check_param[0]) != 0:
        log.error(f"[LASER] Failed parameter checks: {', '.join(laser_check_param)}")
    else:
        log.info("[LASER] Passed parameter checks")

    check_inst(pm, laser)

    if dryrun:
        return None

    # TLS: starts continuous sweep
    laser.write(":SOURCE0:WAV:SWE:STATE 1")
    log.info("[LASER] Start a continuous sweep")

    # Hold execution until sweep finishes
    while int(laser.query(":SOURCE0:WAV:SWE:STATE?")) == 1:
        log.info("[LASER] Sweeping...")
        time.sleep(1)
    
    log.info("[LASER] Sweep finished")
    
    # PM: read logged data
    power_w_all = []
    
    for i in params.channel:
        log.info(f"[PM] Ch.{i}: Read logged measurements")
        pm.write(f":SENSE{i}:FUNC:RES?")
        time.sleep(2)

        power_w_all.append(np.asarray(pm.read_binary_values(container=np.ndarray), dtype=np.float64))
        log.info(f"[PM] Ch.{i}: Log count: {len(power_w_all[-1])}")
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, STOP")
    
    check_inst(pm, laser)
    laser.write(":SOURCE0:POW:STATE 0")
    
    upper_limit = POWER_LIMIT[str(params.pm_range)]
    
    for i, arr_w in zip(params.channel, power_w_all):
        arr_w[arr_w > upper_limit] = np.nan
        if np.all(np.isnan(arr_w)):
            log.warning(f"[PM] Ch.{i}: All measurements are overflown.")
        elif np.any(np.isnan(arr_w)):
            log.warning(f"[PM] Ch.{i}: Some measurements are overflown.")
    
        if np.any(arr_w <= 0):
            log.warning(f"[PM] Ch.{i}: Some measurements are less than or equal to 0.")
            arr_w[arr_w <= 0] = np.nan
    
    return power_w_all

if __name__ == "__main__":
    pm, laser = prep_inst()