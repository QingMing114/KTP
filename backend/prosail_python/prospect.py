import numpy as np
from scipy.special import expi
from prosail_core import calctav
from spectral_data_full import get_spectral_data

def expint(x):
    """指数积分函数"""
    return -expi(-x)


def data_spec_pdb():
    """
    获取光谱数据
    返回的数据格式与MATLAB一致：
    第1列：波长 (400-2500nm)
    第2列：折射率 nr
    第3列：Kab (叶绿素吸收系数)
    第4列：Kcar (类胡萝卜素吸收系数)
    第5列：Kant (花青素吸收系数)
    第6列：KBrown (褐色素吸收系数)
    第7列：Kw (水吸收系数)
    第8列：Km (干物质吸收系数)
    第9列：Es (直接光)
    第10列：Ed (散射光)
    第11列：Rsoil1 (干土壤反射率)
    第12列：Rsoil2 (湿土壤反射率)
    """
    spectral_data = get_spectral_data()
    n_wl = spectral_data.shape[0]
    
    # 生成波长列 (400-2500nm)
    wavelengths = np.arange(400, 400 + n_wl)
    
    # 组合数据：波长 + 光谱数据
    data = np.column_stack([wavelengths, spectral_data])
    
    return data


def prospect_db(N, Cab, Car, Ant, Brown, Cw, Cm):
    """
    PROSPECT-D叶片光学模型
    计算叶片的反射率和透过率
    
    参数:
        N: 叶片结构参数
        Cab: 叶绿素含量 (μg/cm²)
        Car: 类胡萝卜素含量 (μg/cm²)
        Ant: 花青素含量 (μg/cm²)
        Brown: 褐色素含量 (任意单位)
        Cw: 等效水厚度 (cm)
        Cm: 干物质含量 (g/cm²)
    
    返回:
        LRT: [波长, 反射率, 透过率]
    """
    data = data_spec_pdb()
    wavelengths = data[:, 0]
    nr = data[:, 1]
    Kab = data[:, 2]
    Kcar = data[:, 3]
    Kant = data[:, 4]
    KBrown = data[:, 5]
    Kw = data[:, 6]
    Km = data[:, 7]
    
    # 计算总吸收系数
    Kall = (Cab * Kab + Car * Kcar + Ant * Kant + Brown * KBrown + Cw * Kw + Cm * Km) / N
    
    # 找到Kall > 0的索引
    j = Kall > 0
    
    # 初始化tau
    t1 = np.ones_like(Kall)
    t2 = np.ones_like(Kall)
    tau = np.ones_like(Kall)
    
    # 计算tau (只针对Kall > 0的情况)
    t1[j] = (1 - Kall[j]) * np.exp(-Kall[j])
    t2[j] = Kall[j] ** 2 * expint(Kall[j])
    tau[j] = t1[j] + t2[j]
    
    # 计算界面反射率和透过率
    talf = calctav(40, nr)
    ralf = 1 - talf
    t12 = calctav(90, nr)
    r12 = 1 - t12
    t21 = t12 / (nr ** 2)
    r21 = 1 - t21
    
    # 顶层表面
    denom = 1 - r21 * r21 * tau ** 2
    Ta = talf * tau * t21 / denom
    Ra = ralf + r21 * tau * Ta
    
    # 底层表面
    t = t12 * tau * t21 / denom
    r = r12 + r21 * tau * t
    
    # Stokes方程计算N层叶片的性质
    D = np.sqrt((1 + r + t) * (1 + r - t) * (1 - r + t) * (1 - r - t))
    rq = r ** 2
    tq = t ** 2
    a = (1 + rq - tq + D) / (2 * r)
    b = (1 - rq + tq + D) / (2 * t)
    
    bNm1 = b ** (N - 1)
    bN2 = bNm1 ** 2
    a2 = a ** 2
    denom = a2 * bN2 - 1
    Rsub = a * (bN2 - 1) / denom
    Tsub = bNm1 * (a2 - 1) / denom
    
    # 零吸收情况
    j_zero = (r + t) >= 1
    Tsub[j_zero] = t[j_zero] / (t[j_zero] + (1 - t[j_zero]) * (N - 1))
    Rsub[j_zero] = 1 - Tsub[j_zero]
    
    # 组合顶层和底层
    denom = 1 - Rsub * r
    tran = Ta * Tsub / denom
    refl = Ra + Ta * Rsub * t / denom
    
    # 返回结果 [波长, 反射率, 透过率]
    LRT = np.column_stack([wavelengths, refl, tran])
    
    return LRT