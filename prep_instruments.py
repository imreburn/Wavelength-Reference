import pyvisa
import time
import logging

log = logging.getLogger(__name__)

VISA_ADDRESS_POWER_METER    = 'USB0::0x0957::0x3718::DE53500131::0::INSTR'
VISA_ADDRESS_TLS            = 'TCPIP0::100.65.2.45::inst0::INSTR'       

TLS_PASSWORD = 1234

def exceptionHandler(exception):

    log.error('Error information:\n\tAbbreviation: %s\n\tError code: %s\n\tDescription: %s' % \
          (exception.abbreviation, exception.error_code, exception.description))


def get_inst():
    rm = pyvisa.ResourceManager()
    
    try: 
        pm    = rm.open_resource(VISA_ADDRESS_POWER_METER)
        laser = rm.open_resource(VISA_ADDRESS_TLS)
    except pyvisa.VisaIOError as ex:
        log.error('VISA Error')
        exceptionHandler(ex)

    pm.read_termination     = '\n'
    laser.read_termination  = '\n'
    pm.write_termination    = '\n'
    laser.write_termination = '\n'
    log.info("Connected to instruments")
    
    return pm, laser


def reset_inst(pm, laser):
    log.info("[PM] Reset")
    pm.write("*RST")
    
    log.info("[LASER] Reset")
    laser.write("*RST")
    time.sleep(3)


def check_inst(pm=None, laser=None):
    if laser:
        if (n := int(laser.query(":SYST:ERR:COUN?"))) > 0:
            for _ in range(n):
                log.error("[LASER] System error: %s", laser.query(':SYST:ERR?'))
        
        if int(laser.query(":LOCK?")) == 1:
            log.warning("[LASER] Locked. Trying to Unlock")
            laser.write(f":LOCK 0, {TLS_PASSWORD}")
            
        if int(laser.query(":LOCK?")) == 1:
            log.error("[LASER] cannot be unlocked.")
        
        time.sleep(0.5)
        while int(laser.query("*OPC?")) == 0:
            log.warning("[LASER] Device is busy.")
            time.sleep(0.5)
            
    if pm:        
        while True:
            pm_check_error = (pm.query(":SYST:ERR?")).split(',')
            if int(pm_check_error[0]) == 0:
                break
            log.error("[PM] System error: %s", pm_check_error)
        
        time.sleep(0.5)
        while int(pm.query("*OPC?")) == 0:
            log.warning("[PM] Device is busy.")
            time.sleep(0.5)


def init_inst(pm, laser):
    log.info("Initializing instruments...")

    # Laser
    laser.clear()
    laser.write(":STAT:QUES:ENAB 32767")    
    
    # Power Meter
    pm.clear()
    pm.write(":STAT:QUES:ENAB 32767")

    # Identify
    log.info(pm.query("*IDN?"))
    log.info(laser.query("*IDN?"))
    
    log.info("Instruments are ready.")


def prep_inst():
    pm, laser = get_inst()
    reset_inst(pm, laser)
    check_inst(pm, laser)
    init_inst(pm, laser)
    return pm, laser

if __name__ == "__main__":
    pm, laser = prep_inst()