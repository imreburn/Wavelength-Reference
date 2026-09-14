import pyvisa
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px

# ext_spike.py — throwaway. Answers three questions, then gets deleted.
VISA_ADDRESS_POWER_METER    = 'USB0::0x0957::0x3718::DE53500131::0::INSTR'


try:
    import msvcrt  # Windows

    def _read_one_key():
        msvcrt.getch()

except ImportError:
    import termios  # macOS / Linux
    import tty

    def _read_one_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def wait_for_key(prompt="Press any key to continue..."):
    """Block until a single keypress; no Enter needed."""
    print(prompt, end="", flush=True)
    _read_one_key()
    print()


rm = pyvisa.ResourceManager()
pm = rm.open_resource(VISA_ADDRESS_POWER_METER)
pm.read_termination = pm.write_termination = '\n'

pm.write("*RST")
time.sleep(3)

while True:

    wait_for_key("Press any key to start...")

    pm_range = 0

    # ----- Setting Power Meter -----
    # Turn off continuous measurement if set
    pm.write(":INIT1:CONT 0")
    pm.write(":SENS1:FUNC:STAT LOGG, STOP")

    # I don't understand why wavelength(equal to stop wavelength should be set. Does this matter?
    pm.write(":SENSE1:CHAN1:POW:WAVE 1312 NM")
    # I am pretty sure this is not necessary; avg time is set by logging parameter
    pm.write(":SENSE1:CHAN1:POW:ATIME 100 US")
    pm.write(":SENSE1:CHAN1:CORR 0")
    pm.write(":SENSE1:CHAN1:POW:RANGE:AUTO  0")
    pm.write(f":SENSE1:CHAN1:POW:RANGE  {pm_range} DBM")
    pm.write(":SENSE1:CHAN1:POW:UNIT  1")

    print(pm.query(":SENSE1:CHAN1:FUNC:STAT?"))

    # Set trigger configuration 
    pm.write(":TRIG1:OUTP DIS")
    pm.write(":TRIG1:INP  CME")
    pm.write(":TRIG:CONF DEF")

    N = 20000
    at = 100

    pm.write(f":SENSE1:CHAN1:FUNC:PAR:LOGG {N}, {at} US")

    # pm.write(":SENSE1:CHAN1:FUNC:PAR:LOGG 100000, 100 US")

    print(pm.query(":SENSE1:CHAN1:FUNC:STAT?"))

    pm.write(":SENS1:FUNC:STAT LOGG, START")

    wait_for_key("Logging armed. Press any key to start polling...")

    # pm.write(":TRIG 1")

    for _ in range(20):
        msg = (pm.query(":SENSE1:CHAN1:FUNC:STAT?")).split(',')
        print(msg)
        if msg[1] == 'COMPLETE':
            break
        time.sleep(1)

    print(pm.query(":SENSE1:CHAN1:FUNC:STAT?"))

    pm.write(":SENSE1:FUNC:RES?")
    time.sleep(2)

    power = np.asarray(pm.read_binary_values(container=np.ndarray), dtype=np.float64)

    # csv_path = f"power_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    # np.savetxt(csv_path, power, delimiter=",", header="power", comments="", fmt="%.9g")
    # print(f"saved {power.size} points to {csv_path}")

    pm.write(":SENSE1:FUNC:STAT LOGG, STOP")

    # N = 20000
    # at = 100
    speed = 0.5
    w_start = 1312
    w_stop = 1313
    stp_nm = round(speed * at/1e6, 7)

    print(f"step size: {stp_nm * 1000} pm")

    w_stop_tmp = w_start + stp_nm * (N-1)
    w_range = np.linspace(w_start, w_stop_tmp, N).round(7)

    p_dbm = 10 * np.log10(power * 1000)
    # fig, ax = plt.subplots()

    # ax.plot(w_range, power)
    # plt.show()

    print(f"Power Meter Range: {pm_range} dBm")
    print(f"Peak: {w_range[np.argmin(p_dbm)]} nm")
    print(f"Depth: {round(((np.min(p_dbm) - np.max(p_dbm)) * -1), 5)} dB")
    # print(w_range[:5])
    # print(p_dbm[:5])

    fig1 = px.scatter(x=w_range, y=p_dbm)
    fig1.update_traces(mode="lines+markers", marker_size=6)
    fig1.update_xaxes(hoverformat=".5f")
    fig1.update_yaxes(hoverformat=".7f")
    fig1.show()
