import os
import sys
import pyvisa
import time
import numpy as np
import pandas as pd

from prep_instruments import prep_inst

def run(params, pm, laser, dryrun=False):
    wav_start    = params["wav_start"]
    wav_stop     = params["wav_stop"]
    sweep_speed  = params["sweep_speed"]
    source_power = params["tls_power"]
    avg_time     = params["avg_time"]
    num_data     = params["num_data"]
    save_csv     = params["save_csv"]
    file_name    = params["file_name"]

    print("--- Start a test ---")

    # ----- Power Meter -----
    pm.write(":INIT1:CONT 0")
    pm.write(":SENS1:FUNC:STAT LOGG, STOP")
    pm.write(f":SENSE1:CHAN1:POW:WAVE {wav_stop:e}")
    pm.write(f":SENSE1:CHAN1:POW:ATIME {avg_time:e}")
    pm.write(":SENSE1:CHAN1:CORR 0.000000000e+00")
    pm.write(":SENSE1:CHAN1:POW:RANGE:AUTO  0")
    pm.write(":SENSE1:CHAN1:POW:RANGE  10.000000000")
    pm.write(":SENSE1:CHAN1:POW:UNIT  1")
    pm.write(":TRIG1:CHAN1:OUTP DIS")
    pm.write(":TRIG1:CHAN1:INP  CME")
    pm.write(":TRIG:CONF PASS")
    pm.write(f":SENSE1:CHAN1:FUNC:PAR:LOGG {num_data}, {avg_time:e}")

    # ----- Laser -----
        
    laser.write(f":SOURCE0:WAVE  {wav_stop:e}")
    laser.write(":SOURCE0:POWER:UNIT  0")
    laser.write(f":SOURCE0:POWER {source_power:f} dBm")
    laser.write(":SOURCE0:POW:STATE 1")
    laser.write(":TRIG:CONF LOOP")
    laser.write(":TRIG0:INP IGN")
    laser.write(":TRIG0:OUTP SWST")
    laser.write(":SOURCE0:WAV:SWE:LLOG OFF")
    laser.write(":SOURCE0:WAV:SWE:MODE CONT")
    laser.write(":SOURCE0:WAV:SWE:REP ONEW")
    laser.write(f":SOURCE0:WAV:SWE:SPE      {sweep_speed:e}")
    laser.write(f":SOURCE0:WAV:SWE:STAR     {wav_start:e}")
    laser.write(f":SOURCE0:WAV:SWE:STOP     {wav_stop:e}")

    laser_check_param = (laser.query(":SOUR0:WAV:SWE:CHEC?")).split(',')
    if int(laser_check_param[0]) != 0:
        print("[LASER] Failed Parameter Checks: ", laser_check_param[1])
        sys.exit("Exit program")
    else:
        print("[LASER] Passed Parameter Checks")

    if not dryrun:
        # PM: arm logging function before sweep starts
        pm.write(":SENS1:FUNC:STAT LOGG, START")

        # TLS: starts continuous sweep
        laser.write(":SOURCE0:WAV:SWE:STATE 1")
        print("[LASER] Start a continuous sweep")

        # Hold execution until sweep finishes
        while int(laser.query(":SOURCE0:WAV:SWE:STATE?")) == 1:
            print("[LASER] Sweeping...")
            time.sleep(1)

        print("[LASER] Sweep finished")

        # PM: read logged date
        print("[PM] Read logged data")
        pm.write(":SENS1:FUNC:RES?")
        time.sleep(2)
        data_arr = pm.read_binary_values(container=np.ndarray)
        print("[PM] Number of logged data: ", len(data_arr))
        print("--- Test finished ---\n")

        arr_dbm  = 10 * np.log10(data_arr / 1e-3)   # convert: W -> dBm
        arr_dbm *= -1   # power loss? 
        # Generate x-axis
        wav_range = np.linspace(wav_start, wav_stop, num=len(arr_dbm))

        df = pd.DataFrame({"Wavelength": wav_range, "Power": arr_dbm})

        # Save raw data to CSV
        print("Save raw data to CSV? ", save_csv)
        if save_csv == 'y':
            os.makedirs(os.path.join("Test Results", "Raw Data"), exist_ok=True)
            df.to_csv(os.path.join("Test Results", "Raw Data", file_name), index=False)    
            print("Saved to a file: ", file_name, "\n")
        
        pm.write(":SENS1:FUNC:STAT LOGG, STOP")
        return df

if __name__ == "__main__":
    pm, laser = prep_inst()