import numpy as np
from prospect import prospect_db, data_spec_pdb
from prosail_core import campbell, dladgen, volscatt, Jfunc1, Jfunc2, Jfunc3

def prosail(N, Cab, Car, Ant, Cbrown, Cw, Cm, LIDFa, LIDFb, TypeLidf, 
           lai, q, tts, tto, psi, rsoil):
    LRT = prospect_db(N, Cab, Car, Ant, Cbrown, Cw, Cm)
    rho = LRT[:, 1]
    tau = LRT[:, 2]
    
    rd = np.pi / 180
    cts = np.cos(rd * tts)
    cto = np.cos(rd * tto)
    ctscto = cts * cto
    tants = np.tan(rd * tts)
    tanto = np.tan(rd * tto)
    cospsi = np.cos(rd * psi)
    dso = np.sqrt(tants * tants + tanto * tanto - 2 * tants * tanto * cospsi)
    
    if TypeLidf == 1:
        lidf, litab = dladgen(LIDFa, LIDFb)
    elif TypeLidf == 2:
        lidf, litab = campbell(LIDFa)
    else:
        raise ValueError("TypeLidf must be 1 or 2")
    
    ks = 0
    ko = 0
    bf = 0
    sob = 0
    sof = 0
    
    na = len(litab)
    for i in range(na):
        ttl = litab[i]
        ctl = np.cos(rd * ttl)
        
        chi_s, chi_o, frho, ftau = volscatt(tts, tto, psi, ttl)
        
        ksli = chi_s / cts
        koli = chi_o / cto
        
        sobli = frho * np.pi / ctscto
        sofli = ftau * np.pi / ctscto
        bfli = ctl * ctl
        
        ks = ks + ksli * lidf[i]
        ko = ko + koli * lidf[i]
        bf = bf + bfli * lidf[i]
        sob = sob + sobli * lidf[i]
        sof = sof + sofli * lidf[i]
    
    sdb = 0.5 * (ks + bf)
    sdf = 0.5 * (ks - bf)
    dob = 0.5 * (ko + bf)
    dof = 0.5 * (ko - bf)
    ddb = 0.5 * (1 + bf)
    ddf = 0.5 * (1 - bf)
    
    sigb = ddb * rho + ddf * tau
    sigf = ddf * rho + ddb * tau
    att = 1 - sigf
    m2 = (att + sigb) * (att - sigb)
    m2[m2 <= 0] = 0
    m = np.sqrt(m2)
    
    sb = sdb * rho + sdf * tau
    sf = sdf * rho + sdb * tau
    vb = dob * rho + dof * tau
    vf = dof * rho + dob * tau
    w = sob * rho + sof * tau
    
    if lai < 0:
        rddt = rsoil
        rsdt = rsoil
        rdot = rsoil
        rsot = rsoil
        return rdot, rsot, rddt, rsdt
    
    e1 = np.exp(-m * lai)
    e2 = e1 * e1
    rinf = (att - m) / sigb
    rinf2 = rinf * rinf
    re = rinf * e1
    denom = 1 - rinf2 * e2
    
    J1ks = Jfunc1(ks, m, lai)
    J2ks = Jfunc2(ks, m, lai)
    J1ko = Jfunc1(ko, m, lai)
    J2ko = Jfunc2(ko, m, lai)
    
    Ps = (sf + sb * rinf) * J1ks
    Qs = (sf * rinf + sb) * J2ks
    Pv = (vf + vb * rinf) * J1ko
    Qv = (vf * rinf + vb) * J2ko
    
    rdd = rinf * (1 - e2) / denom
    tdd = (1 - rinf2) * e1 / denom
    tsd = (Ps - re * Qs) / denom
    rsd = (Qs - re * Ps) / denom
    tdo = (Pv - re * Qv) / denom
    rdo = (Qv - re * Pv) / denom
    
    tss = np.exp(-ks * lai)
    too = np.exp(-ko * lai)
    z = Jfunc3(ks, ko, lai)
    g1 = (z - J1ks * too) / (ko + m)
    g2 = (z - J1ko * tss) / (ks + m)
    
    Tv1 = (vf * rinf + vb) * g1
    Tv2 = (vf + vb * rinf) * g2
    T1 = Tv1 * (sf + sb * rinf)
    T2 = Tv2 * (sf * rinf + sb)
    T3 = (rdo * Qs + tdo * Ps) * rinf
    
    rsod = (T1 + T2 - T3) / (1 - rinf2)
    
    alf = 1e6
    if q > 0 and (ks + ko) > 0:
        alf = (dso / q) * 2 / (ks + ko)
    
    if alf > 200:
        alf = 200
    
    if alf == 0 or (ks + ko) == 0:
        tsstoo = tss
        sumint = (1 - tss) / (ks * lai + 1e-10)
    else:
        fhot = lai * np.sqrt(ko * ks)
        x1 = 0
        y1 = 0
        f1 = 1
        fint = (1 - np.exp(-alf)) * 0.05
        sumint = 0
        
        for i in range(20):
            if i < 19:
                x2 = -np.log(1 - i * fint + 1e-10) / alf
            else:
                x2 = 1
            
            y2 = -(ko + ks) * lai * x2 + fhot * (1 - np.exp(-alf * x2)) / alf
            f2 = np.exp(y2)
            
            denom = y2 - y1
            if abs(denom) > 1e-10:
                sumint = sumint + (f2 - f1) * (x2 - x1) / (denom)
            x1 = x2
            y1 = y2
            f1 = f2
        
        tsstoo = f1
    
    rsos = w * lai * sumint
    rso = rsos + rsod
    
    dn = 1 - rsoil * rdd
    rddt = rdd + tdd * rsoil * tdd / dn
    rsdt = rsd + (tsd + tss) * rsoil * tdd / dn
    rdot = rdo + tdd * rsoil * (tdo + too) / dn
    rsodt = rsod + ((tss + tsd) * tdo + (tsd + tss * rsoil * rdd) * too) * rsoil / dn
    rsost = rsos + tsstoo * rsoil
    rsot = rsost + rsodt
    
    return rdot, rsot, rddt, rsdt
