import pyvisa
import time
import logging

from constants import VISA_ADDRS, TLS_PASSWORD, PM, LAS

log = logging.getLogger(__name__)

_rm = None

_NAMES = {addr: name for name, addr in VISA_ADDRS.items()}
VISA_TIMEOUT  = 10000
OPC_TRIES     = 20
OPC_INTERVAL  = 0.5
ERR_DRAIN_MAX = 20      # cap on :SYST:ERR? reads, so a stuck queue cannot hang


class InstrumentError(Exception):
    """An instrument did not respond as required: a stuck *OPC?, a lock that
    will not clear, a malformed reply. Callers treat this as a failed run
    rather than a bug, so main.py returns to the config window."""


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


class _InstAdapter(logging.LoggerAdapter):
    """Prefixes each message with the instrument's short name."""
    def process(self, msg, kwargs):
        return f"[{self.extra['name']}] {msg}", kwargs


def inst_name(inst):
    """Short label for logs: the VISA_ADDRS key, else the raw address, else the class name (the stand-ins in inst_dummy have no resource_name)."""
    addr = getattr(inst, "resource_name", "")
    return _NAMES.get(addr, addr or type(inst).__name__)


def inst_log(inst, logger=log):
    """Return a logger that prefixes messages with [POWER METER], [LASER], etc.
    Pass the calling module's logger so %(name)s still names that module."""
    return _InstAdapter(logger, {"name": inst_name(inst)})


def _open(name):
    """Open one instrument by its VISA_ADDRS key."""
    res = get_rm().open_resource(VISA_ADDRS[name])
    res.read_termination  = '\n'
    res.write_termination = '\n'
    res.timeout = VISA_TIMEOUT
    return res


def query_fields(inst, cmd):
    """Query "<cmd>?" and return the reply as stripped fields."""
    reply = [f.strip().strip('"') for f in inst.query(f"{cmd}?").split(',')]
    inst_log(inst).debug("%s -> %s", cmd, reply)
    return reply


def write_and_query(inst, cmd, *args):
    """Send "<cmd> <args>", then log and return what the instrument reports."""
    inst.write(f"{cmd} {', '.join(str(a) for a in args)}" if args else cmd)
    return query_fields(inst, cmd)




def wait_opc(inst):
    """Wait until *OPC? replies 1. Each query blocks up to inst.timeout;
    a reply of 0 is retried a few times before giving up."""
    ilog = inst_log(inst)
    for _ in range(OPC_TRIES):
        if int(inst.query("*OPC?")) == 1:
            ilog.debug("Device is ready")
            return
        ilog.warning("Device is busy")
        time.sleep(OPC_INTERVAL)
    raise InstrumentError(f"[{inst_name(inst)}] *OPC? still 0 after {OPC_TRIES} tries.")

def _unlock_laser(laser):
    """Unlock the TLS so it accepts output commands. Raises if it stays locked."""
    if int(laser.query(":LOCK?")) == 0:
        return
    ilog = inst_log(laser)
    ilog.warning("Locked. Trying to unlock.")
    laser.write(f":LOCK 0, {TLS_PASSWORD}")
    wait_opc(laser)
    if int(laser.query(":LOCK?")) == 1:
        raise InstrumentError(f"[{inst_name(laser)}] cannot be unlocked.")

def _check(inst):
    """Drain the error queue, then wait for pending operations to finish.
    Returns False if the device reported any error."""
    if not inst:
        return True

    ilog = inst_log(inst)
    ok = True
    for _ in range(ERR_DRAIN_MAX):
        reply = inst.query(":SYST:ERR?")
        code, _, msg = reply.partition(',')
        try:
            code = int(code)
        except ValueError:
            raise InstrumentError(
                f"[{inst_name(inst)}] bad :SYST:ERR? reply: {reply!r}")
        if code == 0:
            break
        ilog.error("System error: %s,%s", code, msg)
        ok = False
    else:
        ilog.error("Error queue still not empty after %d reads", ERR_DRAIN_MAX)
        ok = False
    if not ok:
        return False

    wait_opc(inst)
    
    if inst_name(inst) == LAS:
        _unlock_laser(inst)
    
    ilog.info("OK")
    return True


def check_inst(pm=None, laser=None):
    return _check(pm) and _check(laser)


def prep_inst(with_laser=True):
    """Connect and prepare the instruments. Returns (pm, laser); laser is None
    when with_laser is False (external-laser mode, where the program never
    talks to the laser).

    Any error closes whatever was already open and is re-raised, so a failed
    startup never leaves a session behind.
    """
    insts = {}
    try:
        insts[PM] = _open(PM)
        if with_laser:
            insts[LAS] = _open(LAS)

        for res in insts.values():
            ilog = inst_log(res)
            ilog.info("Reset")
            res.write("*RST")
            wait_opc(res)
            res.write(":STAT:QUES:ENAB 32767")
            res.write("*CLS")
            ilog.info(res.query("*IDN?"))
            wait_opc(res)
            
        if with_laser:
            _unlock_laser(insts[LAS])
    except Exception as ex:
        if isinstance(ex, pyvisa.VisaIOError):
            log.error('VISA Error')
            exceptionHandler(ex)
        for res in insts.values():
            res.close()
        raise

    log.info("Instruments are ready." if with_laser else "Power meter is ready.")
    return insts[PM], insts.get(LAS)


def close_inst(pm=None, laser=None):
    if laser:
        try:
            laser.write(":SOURCE0:POW:STATE 0")
        except Exception:
            log.exception("Laser power-off failed")
        laser.close()

    if pm:
        pm.close()
        
    get_rm().close()


if __name__ == "__main__":
    pm, laser = prep_inst()
