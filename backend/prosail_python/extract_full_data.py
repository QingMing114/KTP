#!/usr/bin/env python3
"""
提取MATLAB dataSpec_PDB.m中的完整光谱数据
"""

import re
import numpy as np

# 读取MATLAB文件
with open('../05模型/PROSAIL_D_MATLAB_2017/dataSpec_PDB.m', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

# 提取数据行 (格式: 波长  nr  Kab  Kcar  Kant  KBrown  Kw  Km  Es  Ed  Rsoil1  Rsoil2)
data_rows = []
for line in lines:
    # 匹配数字行
    match = re.match(r'^(\d+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)', line)
    if match:
        # 提取所有列 (跳过波长，只保留后面的11列)
        values = [float(match.group(i)) for i in range(2, 13)]
        data_rows.append(values)

print(f"提取了 {len(data_rows)} 行数据")

# 保存为numpy数组
if len(data_rows) > 0:
    data_array = np.array(data_rows, dtype=np.float64)
    
    # 保存为numpy文件
    np.save('spectral_data.npy', data_array)
    print(f"数据已保存到 spectral_data.npy")
    print(f"数据形状: {data_array.shape}")
    
    # ``spectral_data_full.py`` is the maintained import target. Do not emit a
    # duplicate wrapper module: it had no runtime consumer and inherited a
    # legacy source encoding.
    print("No Python wrapper generated; use spectral_data_full.py at runtime")
else:
    print("未能提取到数据")
