import time
import numpy as np
import logging

from inst_helper import (prep_inst, check_inst, inst_log, wait_opc,
                         write_and_query, query_fields, InstrumentError)
from constants import POWER_LIMIT
from structs import Params

log = logging.getLogger(__name__)

# Number of times run_sweep has been called since this module was imported
# (i.e. since main.py started).
_sweep_count = 0

# How long read_pm waits for the meter to finish its log before giving up.
LOG_DONE_TRIES    = 5
LOG_DONE_INTERVAL = 0.5


class SweepCancelled(Exception):
    """Raised by run_sweep_ext when the user cancels (Esc / Ctrl+C) or the wait
    times out while the power meter is armed. main.py catches it and returns to
    the config window; no data from the run is kept."""


class SweepFailed(InstrumentError):
    """Raised when an instrument cannot deliver the sweep (e.g. the meter never
    finishes its log). Like SweepCancelled, main.py catches it and returns to
    the config window instead of ending the session, but this one is the
    instrument's fault rather than the user's, so it is logged as an error."""

def disarm_pm(pm):
    """Undo arm_pm after a cancel: stop the log and ignore the trigger input, so
    a late trigger from the laser cannot start a log nobody will read.

    The device clear comes first because Ctrl+C can land between the write and
    the read inside pm.query(); the meter's unread reply would otherwise be
    returned by the next query in check_inst.
    """
    pm.clear()
    for i in range(1, 5):
        write_and_query(pm, f":SENSE{i}:FUNC:STAT", "LOGG", "STOP")
        write_and_query(pm, f":TRIG{i}:INP",  "IGN")
        write_and_query(pm, f":TRIG{i}:OUTP", "DIS")
    wait_opc(pm)


def arm_pm(pm, params : Params):
    disarm_pm(pm)
    
    ilog = inst_log(pm, log)
    pm.write(":TRIG:CONF DEF")

    # ----- Power Meter -----
    for i in params.channel:
        ilog.debug("Start setting parameters")
        query_fields(pm, f":SENSE{i}:FUNC:STAT")
        
        # Triggers
        write_and_query(pm, f":TRIG{i}:OUTP", "DIS")
        write_and_query(pm, f":TRIG{i}:INP",  "CME")
        
        wait_opc(pm)
        
        # pm.write(f":INIT{i}:CONT 0")
                
        pm.write(f":SENSE{i}:POW:WAV {(params.wl_st_pad + params.wl_sp_pad)/2:.3f} NM")
        pm.write(f":SENSE{i}:POW:ATIME {params.at_us} US")
        pm.write(f":SENSE{i}:CORR 0")
        pm.write(f":SENSE{i}:POW:REF:STATE OFF")
        pm.write(f":SENSE{i}:POW:RANGE:AUTO  0")
        pm.write(f":SENSE{i}:POW:RANGE  {params.pm_range} DBM")
        pm.write(f":SENSE{i}:POW:UNIT  1")   # W (faster)
        
        wait_opc(pm)
        
        ilog.debug("Now arming the power meter")
        query_fields(pm, f":SENSE{i}:FUNC:STAT")
        
        write_and_query(pm, f":SENSE{i}:FUNC:PAR:LOGG", params.num_data, f"{params.at_us} US")
        
        # pm.write(f":SENSE{i}:FUNC:PAR:LOGG {params.num_data}, {params.at_us} US")
        # PM: arm logging function before sweep starts
        pm.write(f":SENSE{i}:FUNC:STAT LOGG, START")
    
    ilog.info("Logging armed.")
    
    



def logging_complete(pm, params):
    """True once every selected channel has finished its log."""
    return all(query_fields(pm, f":SENSE{i}:FUNC:STAT")[1] == "COMPLETE" for i in params.channel)


def read_pm(pm, params : Params):
    ilog = inst_log(pm, log)
    
    # The meter can lag a moment behind the laser's sweep-state flag, so give it
    # a short grace period before treating the log as failed.
    for _ in range(LOG_DONE_TRIES):
        if logging_complete(pm, params):
            ilog.info("Logging completed")
            break
        time.sleep(LOG_DONE_INTERVAL)
    else:
        disarm_pm(pm)   # leave no armed channel behind for the next run
        raise SweepFailed(
            f"logging still in progress after "
            f"{LOG_DONE_TRIES * LOG_DONE_INTERVAL:.1f} s")

    power_w_all = []
    upper_limit = POWER_LIMIT[str(params.pm_range)]
    
    for i in params.channel:
        ilog.info(f"Ch.{i}: Read logged measurements")
        # pm.write(f":SENSE{i}:FUNC:RES?")
        power_w_all.append(np.asarray(pm.query_binary_values(f":SENSE{i}:FUNC:RES?", container=np.ndarray), dtype=np.float64))
        wait_opc(pm)
        ilog.info(f"Ch.{i}: Log count: {len(power_w_all[-1])}")
        
    for i, arr_w in zip(params.channel, power_w_all):
        arr_w[arr_w > upper_limit] = np.nan
        if np.all(np.isnan(arr_w)):
            ilog.warning(f"Ch.{i}: All measurements are overflown.")
        elif np.any(np.isnan(arr_w)):
            ilog.warning(f"Ch.{i}: Some measurements are overflown.")
        if np.any(arr_w <= 0):
            ilog.warning(f"Ch.{i}: Some measurements are less than or equal to 0.")
            arr_w[arr_w <= 0] = np.nan
    
    disarm_pm(pm)
    
    return power_w_all

def sweep_laser(laser, params: Params):
    ilog = inst_log(laser, log)
    
    laser.write(f":SOURCE0:WAVE  {params.wl_st_pad:.3f} NM")
    wait_opc(laser)
    
    laser.write(":SOURCE0:POWER:UNIT  0")   # dBM
    laser.write(f":SOURCE0:POWER {params.tls_dbm} DBM")
    laser.write(":SOURCE0:POW:STATE 1")
    wait_opc(laser)
    
    # laser.write(":SOURCE0:WAV:SWE:LLOG OFF")
    write_and_query(laser, ":SOURCE0:WAV:SWE:LLOG", "OFF")
    
    laser.write(":SOURCE0:WAV:SWE:MODE CONT")
    laser.write(":SOURCE0:WAV:SWE:REP ONEW")
    laser.write(":SOURCE0:WAV:SWE:CYCL 1")
    laser.write(":SOURCE0:WAV:SWE:DWEL 0")
    wait_opc(laser)
    
    laser.write(f":SOURCE0:WAV:SWE:SPE      {params.speed} NM/S")
    laser.write(f":SOURCE0:WAV:SWE:STAR     {params.wl_st_pad:.3f} NM")
    laser.write(f":SOURCE0:WAV:SWE:STOP     {params.wl_sp_pad:.3f} NM")
    wait_opc(laser)
    
    # Trigger
    write_and_query(laser, ":TRIG:CONF", "DEF")
    write_and_query(laser, ":TRIG0:INP", "IGN")
    write_and_query(laser, ":TRIG0:OUTP", "SWST")
    # laser.write(":TRIG:CONF DEF")
    # laser.write(":TRIG0:INP IGN")
    # laser.write(":TRIG0:OUTP SWST")   

    # ----- Laser: check parameter errors -----
    laser_check_param = query_fields(laser, ":SOUR0:WAV:SWE:CHEC")
    if int(laser_check_param[0]) != 0:
        raise SweepFailed(f"[LASER] Failed parameter checks: {', '.join(laser_check_param)}")

    wait_opc(laser)
    # ----- Laser: starts continuous sweep
    ilog.info("Start a continuous sweep")
    laser.write(":SOURCE0:WAV:SWE:STATE 1")

    # Hold execution until sweep finishes
    while int(laser.query(":SOURCE0:WAV:SWE:STATE?")) == 1:
        ilog.info("Sweeping...")
        time.sleep(1)
    
    wait_opc(laser)
    ilog.info("Sweep finished")

    # Safety: turn off laser after each run
    # Changed: the shutter remains open for the power readout window
    # laser.write(":SOURCE0:POW:STATE 0")
    

def run_sweep(pm, laser, params: Params):
    """
    Returns a list of np 1-d arrays with the order matching with param.channel. (e.g. [Ch.1, Ch.2, Ch.3, Ch.4])
    """
    global _sweep_count
    _sweep_count += 1
    log.info(f"--- Running instruments (sweep #{_sweep_count}) ---")
    
    check_inst(pm, laser)

    arm_pm(pm, params)
    
    sweep_laser(laser, params)
    
    check_inst(pm, laser)
    
    return read_pm(pm, params)


if __name__ == "__main__":
    pm, laser = prep_inst()