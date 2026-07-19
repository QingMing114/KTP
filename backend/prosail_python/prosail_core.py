import numpy as np
from scipy.special import expi

def calctav(alfa, nr):
    rd = np.pi / 180
    n2 = nr ** 2
    np_val = n2 + 1
    nm = n2 - 1
    
    sa = np.sin(alfa * rd)
    sa2 = sa ** 2
    
    a = (nr + 1) ** 2 / 2
    k = -nm ** 2 / 4
    
    b2 = sa2 - np_val / 2
    
    inner = b2 ** 2 + k
    inner = np.maximum(inner, 0)
    b1 = (alfa != 90) * np.sqrt(inner)
    b = b1 - b2
    
    b3 = b ** 3
    a3 = a ** 3
    
    with np.errstate(divide='ignore', invalid='ignore'):
        ts = (k ** 2 / (6 * b3) + k / b - b / 2) - (k ** 2 / (6 * a3) + k / a - a / 2)
        ts = np.nan_to_num(ts, nan=0.0, posinf=0.0, neginf=0.0)
        
        tp1 = -2 * n2 * (b - a) / (np_val ** 2)
        
        with np.errstate(divide='ignore', invalid='ignore'):
            tp2 = -2 * n2 * np_val * np.log(np.abs(b) / np.abs(a)) / (nm ** 2 + 1e-10)
            tp2 = np.nan_to_num(tp2, nan=0.0, posinf=0.0, neginf=0.0)
        
        tp3 = n2 * (1 / b - 1 / a) / 2
        
        denom_4 = np_val ** 3 * (nm ** 2 + 1e-10)
        tp4 = 16 * n2 ** 2 * (n2 ** 2 + 1) * np.log(np.abs(2 * np_val * b - nm ** 2) / np.abs(2 * np_val * a - nm ** 2 + 1e-10)) / denom_4
        tp4 = np.nan_to_num(tp4, nan=0.0, posinf=0.0, neginf=0.0)
        
        denom_5 = np_val ** 3
        tp5 = 16 * n2 ** 3 * (1 / (2 * np_val * b - nm ** 2 + 1e-10) - 1 / (2 * np_val * a - nm ** 2 + 1e-10)) / denom_5
        tp5 = np.nan_to_num(tp5, nan=0.0, posinf=0.0, neginf=0.0)
        
        tp = tp1 + tp2 + tp3 + tp4 + tp5
        
        denom_tav = 2 * sa2
        tav = (ts + tp) / denom_tav
        tav = np.nan_to_num(tav, nan=0.0, posinf=0.0, neginf=0.0)
    
    return tav


def dcum(a, b, t):
    rd = np.pi / 180
    if a >= 1:
        f = 1 - np.cos(rd * t)
    else:
        eps = 1e-8
        delx = 1
        x = 2 * rd * t
        p = x
        while delx >= eps:
            y = a * np.sin(x) + 0.5 * b * np.sin(2 * x)
            dx = 0.5 * (y - x + p)
            x = x + dx
            delx = abs(dx)
        f = (2 * y + p) / np.pi
    return f


def dladgen(a, b):
    litab = np.array([5., 15., 25., 35., 45., 55., 65., 75., 81., 83., 85., 87., 89.])
    freq = np.zeros(13)
    
    for i1 in range(8):
        t = (i1 + 1) * 10
        freq[i1] = dcum(a, b, t)
    
    for i2 in range(8, 12):
        t = 80. + (i2 - 7) * 2.
        freq[i2] = dcum(a, b, t)
    
    freq[12] = 1
    for i in range(12, 0, -1):
        freq[i] = freq[i] - freq[i - 1]
    
    return freq, litab


def campbell(ala):
    tx1 = np.array([10., 20., 30., 40., 50., 60., 70., 80., 82., 84., 86., 88., 90.])
    tx2 = np.array([0., 10., 20., 30., 40., 50., 60., 70., 80., 82., 84., 86., 88.])
    
    litab = (tx2 + tx1) / 2
    n = len(litab)
    tl1 = tx1 * (np.pi / 180)
    tl2 = tx2 * (np.pi / 180)
    excent = np.exp(-1.6184e-5 * ala ** 3 + 2.1145e-3 * ala ** 2 - 1.2390e-1 * ala + 3.2491)
    
    freq = np.zeros(n)
    for i in range(n):
        x1 = excent / np.sqrt(1 + excent ** 2 * np.tan(tl1[i]) ** 2)
        x2 = excent / np.sqrt(1 + excent ** 2 * np.tan(tl2[i]) ** 2)
        
        if excent == 1:
            freq[i] = abs(np.cos(tl1[i]) - np.cos(tl2[i]))
        else:
            alpha = excent / np.sqrt(abs(1 - excent ** 2))
            alpha2 = alpha ** 2
            x12 = x1 ** 2
            x22 = x2 ** 2
            
            if excent > 1:
                alpx1 = np.sqrt(alpha2 + x12)
                alpx2 = np.sqrt(alpha2 + x22)
                dum = x1 * alpx1 + alpha2 * np.log(x1 + alpx1)
                freq[i] = abs(dum - (x2 * alpx2 + alpha2 * np.log(x2 + alpx2)))
            else:
                almx1 = np.sqrt(alpha2 - x12)
                almx2 = np.sqrt(alpha2 - x22)
                dum = x1 * almx1 + alpha2 * np.arcsin(np.clip(x1 / alpha, -1, 1))
                freq[i] = abs(dum - (x2 * almx2 + alpha2 * np.arcsin(np.clip(x2 / alpha, -1, 1))))
    
    sum0 = np.sum(freq)
    freq0 = freq / sum0
    
    return freq0, litab


def Jfunc1(k, l, t):
    k = np.asarray(k)
    l = np.asarray(l)
    del_val = (k - l) * t
    
    if del_val.size == 1 and np.isscalar(del_val):
        del_val = np.array([del_val])
        k = np.array([k]) if np.isscalar(k) else k
        l = np.array([l]) if np.isscalar(l) else l
        scalar_input = True
    else:
        scalar_input = False
    
    Jout = np.zeros_like(del_val, dtype=float)
    
    mask = np.abs(del_val) > 1e-3
    if np.any(mask):
        k_arr = np.asarray(k)
        l_arr = np.asarray(l)
        Jout[mask] = (np.exp(-l_arr[mask] * t) - np.exp(-k_arr * t)) / (k_arr - l_arr[mask])
    
    mask2 = np.abs(del_val) <= 1e-3
    if np.any(mask2):
        k_arr = np.asarray(k)
        l_arr = np.asarray(l)
        Jout[mask2] = (0.5 * t * (np.exp(-k_arr * t) + np.exp(-l_arr[mask2] * t)) * 
                       (1 - del_val[mask2] * del_val[mask2] / 12))
    
    if scalar_input:
        return float(Jout[0]) if Jout.size == 1 else Jout
    return Jout


def Jfunc2(k, l, t):
    k = np.asarray(k)
    l = np.asarray(l)
    return (1 - np.exp(-(k + l) * t)) / (k + l)


def Jfunc3(k, l, t):
    k = np.asarray(k)
    l = np.asarray(l)
    return (1 - np.exp(-(k + l) * t)) / (k + l)


def volscatt(tts, tto, psi, ttl):
    rd = np.pi / 180
    costs = np.cos(rd * tts)
    costo = np.cos(rd * tto)
    sints = np.sin(rd * tts)
    sinto = np.sin(rd * tto)
    cospsi = np.cos(rd * psi)
    psir = rd * psi
    costl = np.cos(rd * ttl)
    sintl = np.sin(rd * ttl)
    
    cs = costl * costs
    co = costl * costo
    ss = sintl * sints
    so = sintl * sinto
    
    cosbts = 5
    if abs(ss) > 1e-6:
        cosbts = -cs / ss
    
    cosbto = 5
    if abs(so) > 1e-6:
        cosbto = -co / so
    
    if abs(cosbts) < 1:
        bts = np.arccos(np.clip(cosbts, -1, 1))
        ds = ss
    else:
        bts = np.pi
        ds = cs
    
    chi_s = 2 / np.pi * ((bts - np.pi * 0.5) * cs + np.sin(bts) * ss)
    
    if abs(cosbto) < 1:
        bto = np.arccos(np.clip(cosbto, -1, 1))
        doo = so
    elif tto < 90:
        bto = np.pi
        doo = co
    else:
        bto = 0
        doo = -co
    
    chi_o = 2 / np.pi * ((bto - np.pi * 0.5) * co + np.sin(bto) * so)
    
    btran1 = abs(bts - bto)
    btran2 = np.pi - abs(bts + bto - np.pi)
    
    if psir <= btran1:
        bt1 = psir
        bt2 = btran1
        bt3 = btran2
    else:
        bt1 = btran1
        if psir <= btran2:
            bt2 = psir
            bt3 = btran2
        else:
            bt2 = btran2
            bt3 = psir
    
    t1 = 2 * cs * co + ss * so * cospsi
    t2 = 0
    if bt2 > 0:
        t2 = np.sin(bt2) * (2 * ds * doo + ss * so * np.cos(bt1) * np.cos(bt3))
    
    denom = 2 * np.pi ** 2
    frho = ((np.pi - bt2) * t1 + t2) / denom
    ftau = (-bt2 * t1 + t2) / denom
    
    if frho < 0:
        frho = 0
    
    if ftau < 0:
        ftau = 0
    
    return chi_s, chi_o, frho, ftau


def expint(x):
    return -expi(-x)