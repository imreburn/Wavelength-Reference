import time
import numpy as np
import logging

from inst_helper import prep_inst, check_inst
from constants import POWER_LIMIT
from structs import Params

log = logging.getLogger(__name__)

# Number of times run_sweep has been called since this module was imported
# (i.e. since main.py started).
_sweep_count = 0


class SweepCancelled(Exception):
    """Raised by run_sweep_ext when the user cancels (Esc / Ctrl+C) or the wait
    times out while the power meter is armed. main.py catches it and returns to
    the config window; no data from the run is kept."""


def arm_pm(pm, params : Params):
    pm.write(f":TRIG:CONF DEF")

    # ----- Power Meter -----
    for i in params.channel:
        pm.write(f":INIT{i}:CONT 0")
        
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, STOP")
        
        pm.write(f":SENSE{i}:POW:WAV {(params.wl_st_pad + params.wl_sp_pad)/2:.3f} NM")
        pm.write(f":SENSE{i}:POW:ATIME {params.at_us} US")
        pm.write(f":SENSE{i}:CORR 0")
        pm.write(f":SENSE{i}:POW:REF:STATE OFF")
        pm.write(f":SENSE{i}:POW:RANGE:AUTO  0")
        pm.write(f":SENSE{i}:POW:RANGE  {params.pm_range} DBM")
        pm.write(f":SENSE{i}:POW:UNIT  1")   # W (faster)
        
        pm.write(f":TRIG{i}:OUTP DIS")
        pm.write(f":TRIG{i}:INP  CME")
        
        pm.write(f":SENSE{i}:FUNC:PAR:LOGG {params.num_data}, {params.at_us} US")
        # PM: arm logging function before sweep starts
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, START")
        print(f"Ch {i}:", pm.query(f":SENSE{i}:FUNC:STAT?"))
    
    log.info("[PM] Logging armed.")
    
    
def disarm_pm(pm, params : Params):
    """Undo arm_pm after a cancel: stop the log and ignore the trigger input, so
    a late trigger from the laser cannot start a log nobody will read.

    The device clear comes first because Ctrl+C can land between the write and
    the read inside pm.query(); the meter's unread reply would otherwise be
    returned by the next query in check_inst.
    """
    pm.clear()
    for i in params.channel:
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, STOP")
        pm.write(f":TRIG{i}:INP IGN")


def logging_complete(pm, params):
    """True once every selected channel has finished its log."""
    return all(pm.query(f":SENSE{i}:FUNC:STAT?").split(',')[1] == "COMPLETE" for i in params.channel)


def read_pm(pm, params : Params):
    power_w_all = []
    upper_limit = POWER_LIMIT[str(params.pm_range)]
    
    for i in params.channel:
        log.info(f"[PM] Ch.{i}: Read logged measurements")
        pm.write(f":SENSE{i}:FUNC:RES?")
        time.sleep(2)

        power_w_all.append(np.asarray(pm.read_binary_values(container=np.ndarray), dtype=np.float64))
        log.info(f"[PM] Ch.{i}: Log count: {len(power_w_all[-1])}")
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, STOP")    
        
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


def run_sweep(pm, laser, params: Params, dryrun=False):
    """
    Returns a list of np 1-d arrays with the order matching with param.channel. (e.g. [Ch.1, Ch.2, Ch.3, Ch.4])
    """
    global _sweep_count
    _sweep_count += 1
    log.info(f"--- Running instruments (sweep #{_sweep_count}) ---")
    
    check_inst(pm, laser)

    arm_pm(pm, params)
    
    # ----- Laser -----
    laser.write(f":SOURCE0:WAVE  {params.wl_st_pad:.3f} NM")
    time.sleep(0.1)
    
    # if (w := (round(float(laser.query(":SOURCE0:WAVE?"))*1e9), 5)) != params.wl_st_pad:
    #     log.warning(f"[LASER] The current wavelength: {w}. Laser is still being adjusted.")
        
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
    laser.write(f":SOURCE0:WAV:SWE:STAR     {params.wl_st_pad:.3f} NM")
    laser.write(f":SOURCE0:WAV:SWE:STOP     {params.wl_sp_pad:.3f} NM")

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

    # Safety: turn off laser after each run
    # Changed: the shutter remains open for the power readout window
    # laser.write(":SOURCE0:POW:STATE 0")
        
    if logging_complete(pm, params):
        log.info("[PM] Logging completed")
    else:
        log.warning("[PM] Logging NOT completed")
        raise Exception
    
    check_inst(pm, laser)
    
    return read_pm(pm, params)


if __name__ == "__main__":
    pm, laser = prep_inst()