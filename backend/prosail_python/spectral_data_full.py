import numpy as np
import os

def get_spectral_data():
    """
    从MATLAB dataSpec_PDB.m提取的完整光谱数据
    共2101个波长 (400-2500nm)
    列顺序与MATLAB一致：
    nr, Kab, Kcar, Kant, KBrown, Kw, Km, Es, Ed, Rsoil1, Rsoil2
    """
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(current_dir, 'spectral_data.npy')
    
    return np.load(data_file)
