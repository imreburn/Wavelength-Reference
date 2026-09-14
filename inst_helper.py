import pyvisa
import time
import logging

from constants import VISA_ADDRESS_POWER_METER, VISA_ADDRESS_TLS, TLS_PASSWORD

log = logging.getLogger(__name__)

_rm = None

def get_rm():
    """Lazily create the VISA ResourceManager on first use.

    Deferring this avoids requiring a VISA backend at import time, so modules
    that only need constants can import them from `constants` without an
    instrument backend present.
    """
    global _rm
    if _rm is None:
        _rm = pyvisa.ResourceManager()
    return _rm

def exceptionHandler(exception):

    log.error('Error information:\n\tAbbreviation: %s\n\tError code: %s\n\tDescription: %s' % \
          (exception.abbreviation, exception.error_code, exception.description))


def _open(address):
    res = get_rm().open_resource(address)
    res.read_termination  = '\n'
    res.write_termination = '\n'
    return res


def _check_laser(laser=None):
    if laser:
        if (n := int(laser.query(":SYST:ERR:COUN?"))) > 0:
            for _ in range(n):
                log.error("[LASER] System error: %s", laser.query(':SYST:ERR?'))
            return False
        
        if int(laser.query(":LOCK?")) == 1:
            log.warning("[LASER] Locked. Trying to Unlock")
            laser.write(f":LOCK 0, {TLS_PASSWORD}")
            
        if int(laser.query(":LOCK?")) == 1:
            log.error("[LASER] cannot be unlocked.")
        
        time.sleep(0.5)
        while int(laser.query("*OPC?")) == 0:
            log.warning("[LASER] Device is busy.")
            time.sleep(0.5)
        
        log.info("[LASER] OK")
    return True


def _check_pm(pm=None):
    pm_ok = True
    if pm:        
        while True:
            pm_check_error = (pm.query(":SYST:ERR?")).split(',')
            if int(pm_check_error[0]) == 0:
                break
            log.error("[PM] System error: %s", pm_check_error)
            pm_ok = False
        if not pm_ok:
            return pm_ok
        
        time.sleep(0.5)
        while int(pm.query("*OPC?")) == 0:
            log.warning("[PM] Device is busy.")
            time.sleep(0.5)
    
        log.info("[PM] OK")
    return pm_ok


def check_inst(pm=None, laser=None):
    return _check_pm(pm) and _check_laser(laser)


def prep_pm():
    """Open, reset, check and initialize the power meter."""
    pm = _open(VISA_ADDRESS_POWER_METER)
    log.info("[PM] Reset")
    pm.write("*RST")
    time.sleep(3)
    _check_pm(pm)
    pm.clear()
    pm.write(":STAT:QUES:ENAB 32767")
    log.info(pm.query("*IDN?"))
    return pm


def prep_laser():
    """Open, reset, check (incl. unlock) and initialize the TLS."""
    laser = _open(VISA_ADDRESS_TLS)
    log.info("[LASER] Reset")
    laser.write("*RST")
    time.sleep(3)
    _check_laser(laser)
    laser.clear()
    laser.write(":STAT:QUES:ENAB 32767")
    log.info(laser.query("*IDN?"))
    return laser


def close_pm(pm):
    _check_pm(pm)
    pm.close()


def close_laser(laser):
    _check_laser(laser)
    # Safety: laser off before the session drops. With the per-sweep power-off
    # in run_sweep disabled (shutter stays open for the readout window), this
    # is the power-off at exit.
    laser.write(":SOURCE0:POW:STATE 0")
    laser.close()


def prep_inst(with_laser=True):
    """Connect and prepare the instruments. Returns (pm, laser); laser is None
    when with_laser is False (external-laser mode, where the program never
    talks to the laser).

    A VISA error closes the PM session if it was already open and is re-raised.
    The old version logged it and fell through with `pm` unbound, so a
    NameError hid the real cause.
    """
    pm = laser = None
    try:
        pm = prep_pm()
        if with_laser:
            laser = prep_laser()
    except pyvisa.VisaIOError as ex:
        log.error('VISA Error')
        exceptionHandler(ex)
        if pm:
            pm.close()
        raise
    log.info("Instruments are ready." if with_laser else "Power meter is ready.")
    return pm, laser

def close_inst(pm=None, laser=None):
    if laser:
        close_laser(laser)   # first, so the laser goes off as early as possible
    if pm:
        close_pm(pm)
    get_rm().close()

if __name__ == "__main__":
    pm, laser = prep_inst()