import pyvisa
import time

def prep_inst():
    rm = pyvisa.ResourceManager()
    rm.list_resources()

    pm    = rm.open_resource('USB0::0x0957::0x3718::DE53500131::0::INSTR')
    laser = rm.open_resource('TCPIP0::100.65.2.45::inst0::INSTR')

    pm.read_termination    = '\n'
    laser.read_termination = '\n'
    
    return pm, laser

def reset_inst(pm, laser):
    """ Reset Instruments; Do only if necessary """
    pm.write("*RST")
    laser.write("*RST")
    time.sleep(2)
