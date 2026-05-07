import os
import pyvisa
import time
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from reset import reset_inst
from plot import plot_data, simple_analysis


def run(params):
    wav_start    = params["wav_start"]
    wav_stop     = params["wav_stop"]
    sweep_speed  = params["sweep_speed"]
    source_power = params["tls_power"]
    avg_time     = params["avg_time"]
    num_data     = params["num_data"]
    save_csv     = params["save_csv"]
    file_name    = params["file_name"]

    rm = pyvisa.ResourceManager()
    rm.list_resources()

    pm    = rm.open_resource('USB0::0x0957::0x3718::DE53500131::0::INSTR')
    laser = rm.open_resource('TCPIP0::100.65.2.45::inst0::INSTR')

    pm.read_termination    = '\n'
    laser.read_termination = '\n'

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

    print(laser.query(":SOUR0:WAV:SWE:CHEC?"))

    pm.write(":SENS1:FUNC:STAT LOGG, START")
    laser.write(":SOURCE0:WAV:SWE:STATE 1")
    print("Sweep start")

    while int(laser.query(":SOURCE0:WAV:SWE:STATE?")) == 1:
        print("Laser sweeping...")
        time.sleep(1)

    print("Sweep finished")

    pm.write(":SENS1:FUNC:RES?")
    time.sleep(1)

    data_arr = pm.read_binary_values(container=np.ndarray)
    arr_dbm  = 10 * np.log10(data_arr / 1e-3)   # convert to dBm
    arr_dbm *= -1   # power loss? 
    wav_range = np.linspace(wav_start, wav_stop, num=len(arr_dbm))

    
    df = pd.DataFrame({"Wavelength": wav_range, "Power": arr_dbm})

    # Save result to
    if save_csv == 'y':
        os.makedirs("Measurements", exist_ok=True)
        df.to_csv(os.path.join("Measurements", file_name), index=False)    
    
    
    # plot_data(df)
    simple_analysis(df)