import numpy as np

def get_spectral_data():
    """
    从MATLAB dataSpec_PDB.m提取的完整光谱数据
    共 2101 个波长 (400-2500nm)
    列顺序与MATLAB一致：
    nr, Kab, Kcar, Kant, KBrown, Kw, Km, Es, Ed, Rsoil1, Rsoil2
    """
