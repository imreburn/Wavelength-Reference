import pyvisa
import time

def reset_inst(PM, TLS):
    """ Reset Instruments; Do only if necessary """
    PM.write("*RST")
    TLS.write("*RST")
    time.sleep(2)

if __name__ == "__main__":
    rm = pyvisa.ResourceManager()
    rm.list_resources()

    # Get instruments
    # Power Meter
    pm = rm.open_resource('USB0::0x0957::0x3718::DE53500131::0::INSTR')
    # Tunable Laser Source
    laser = rm.open_resource('TCPIP0::100.65.2.45::inst0::INSTR')

    # Reset
    reset_inst(pm, laser)
