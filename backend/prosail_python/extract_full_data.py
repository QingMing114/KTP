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
    
    # 同时生成Python代码文件
    with open('spectral_data_generated.py', 'w') as f:
        f.write("import numpy as np\n\n")
        f.write("def get_spectral_data():\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    从MATLAB dataSpec_PDB.m提取的完整光谱数据\n")
        f.write(f"    共 {len(data_rows)} 个波长 (400-2500nm)\n")
        f.write(f"    列顺序与MATLAB一致：\n")
        f.write(f"    nr, Kab, Kcar, Kant, KBrown, Kw, Km, Es, Ed, Rsoil1, Rsoil2\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    return np.load('{spectral_data.npy}')\n")
    
    print(f"Python代码已保存到 spectral_data_generated.py")
else:
    print("未能提取到数据")
