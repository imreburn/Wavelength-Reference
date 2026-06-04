import pyvisa
import time

VISA_ADDRESS_POWER_METER    = 'USB0::0x0957::0x3718::DE53500131::0::INSTR'
VISA_ADDRESS_TLS            = 'TCPIP0::100.65.2.45::inst0::INSTR'       

def exceptionHandler(exception):

    print('Error information:\n\tAbbreviation: %s\n\tError code: %s\n\tDescription: %s' % \
          (exception.abbreviation, exception.error_code, exception.description))

def get_inst():
    print("Connecting to instruments...")
    rm = pyvisa.ResourceManager()
    
    try: 
        pm    = rm.open_resource(VISA_ADDRESS_POWER_METER)
        laser = rm.open_resource(VISA_ADDRESS_TLS)
    except visa.VisaIOError as ex:
        print('VISA Error')
        exceptionHandler(ex)

    pm.read_termination    = '\n'
    laser.read_termination = '\n'   

    print(pm.query("*IDN?"))
    print(laser.query("*IDN?"))

    print("Connected\n")
    return pm, laser


def reset_inst(pm, laser):
    print("[PM] Reset")
    pm.write("*RST")
    
    print("[LASER] Reset")
    laser.write("*RST")
    time.sleep(3)


def init_inst(pm, laser):
    print("Initializing instruments...")
    reset_inst(pm, laser)

    # Laser
    if (int(laser.query(":LOCK?")) == 1):
        print("[LASER] TLS Locked. Unlock")
        laser.write(":LOCK 0, 1234")

    laser.write(":STAT:QUES:ENAB 32767")    
    
    # Power Meter
    pm.write(":STAT:QUES:ENAB 32767")

    print("Instruments ready")


def prep_inst():
    pm, laser = get_inst()
    init_inst(pm, laser)

    return pm, laser

if __name__ == "__main__":
    pm, laser = prep_inst()