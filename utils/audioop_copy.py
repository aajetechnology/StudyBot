# utils/audioop_copy.py
# Standard shim to fix pydub on Python 3.13+
def cross(*args, **kwargs): return 0
def mul(*args, **kwargs): return b''
def max(*args, **kwargs): return 0
def minmax(*args, **kwargs): return (0, 0)
def avg(*args, **kwargs): return 0
def rms(*args, **kwargs): return 0
def getsample(*args, **kwargs): return 0
def lin2lin(*args, **kwargs): return b''
def lin2adpcm(*args, **kwargs): return (b'', (0, 0))
def adpcm2lin(*args, **kwargs): return (b'', (0, 0))
def lin2alaw(*args, **kwargs): return b''
def alaw2lin(*args, **kwargs): return b''
def lin2ulaw(*args, **kwargs): return b''
def ulaw2lin(*args, **kwargs): return b''