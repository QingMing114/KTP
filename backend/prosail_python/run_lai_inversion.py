#!/usr/bin/env python3
"""
PROSAIL LAI反演主程序
使用真实卫星数据进行LAI反演并与地面实测数据验证
"""

import sys
sys.path.append('.')

import numpy as np
import rasterio
from rasterio.transform import from_origin
import pandas as pd
from prosail_api import PROSAILEngine, create_default_params
from datetime import datetime
import os

print("=" * 70)
print("PROSAIL LAI反演系统")
print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ============================================================================
# 步骤1: 读取输入数据
# ============================================================================
print("\n【步骤1】读取输入数据")
print("-" * 70)

# 1.1 读取卫星数据
satellite_path = '../04中间产品（预处理）/张掖/zhangye.tif'
print(f"读取卫星数据: {satellite_path}")

with rasterio.open(satellite_path) as src:
    img = src.read()
    profile = src.profile
    transform = src.transform
    crs = src.crs
    
    print(f"  图像尺寸: {img.shape}")
    print(f"  数据类型: {src.dtypes[0]}")
    print(f"  坐标系统: {crs}")
    print(f"  地理范围: {src.bounds}")

# 转换数据类型 (uint16 -> float, 除以10000)
img_float = img.astype(np.float32) / 10000.0
img_float = np.clip(img_float, 0, 1)

print(f"  反射率范围: [{img_float.min():.4f}, {img_float.max():.4f}]")

# 提取波段
b2 = img_float[0]  # 490nm 蓝光
b3 = img_float[1]  # 560nm 绿光
b4 = img_float[2]  # 665nm 红光
b8 = img_float[3]  # 842nm 近红外
ndvi = img_float[4] if img.shape[0] > 4 else (b8 - b4) / (b8 + b4 + 1e-10)

print(f"  B2 (490nm): [{b2.min():.4f}, {b2.max():.4f}]")
print(f"  B3 (560nm): [{b3.min():.4f}, {b3.max():.4f}]")
print(f"  B4 (665nm): [{b4.min():.4f}, {b4.max():.4f}]")
print(f"  B8 (842nm): [{b8.min():.4f}, {b8.max():.4f}]")
print(f"  NDVI: [{ndvi.min():.4f}, {ndvi.max():.4f}]")

# 1.2 读取地面实测数据
measured_path = '../02地面测量数据/张掖/LAI2200/张掖.xlsx'
print(f"\n读取地面实测数据: {measured_path}")

df_measured = pd.read_excel(measured_path)
print(f"  实测点数: {len(df_measured)}")
print(f"  数据列: {df_measured.columns.tolist()}")
print(f"  LAI范围: [{df_measured['LAI'].min():.2f}, {df_measured['LAI'].max():.2f}]")

# 显示前5行
print(f"\n  前5个实测点:")
for i in range(min(5, len(df_measured))):
    row = df_measured.iloc[i]
    print(f"    点{i+1}: LAI={row['LAI']:.2f}, 纬度={row['纬度']:.6f}, 经度={row['经度']:.6f}")

# ============================================================================
# 步骤2: 构建或加载查找表
# ============================================================================
print("\n【步骤2】构建/加载查找表")
print("-" * 70)

engine = PROSAILEngine()
lut_file = 'zhangye_lut.pkl'

if os.path.exists(lut_file):
    print(f"加载已存在的查找表: {lut_file}")
    engine.load_lut(lut_file)
else:
    print("构建新的查找表...")
    
    params = create_default_params()
    params['bands'] = [490, 560, 665, 842]
    
    # 设置参数范围（针对玉米作物优化）
    params['parameters']['LAI'] = {'min': 0, 'max': 6, 'step': 0.5}
    params['parameters']['Cab'] = {'min': 20, 'max': 80, 'step': 10}
    params['parameters']['Car'] = {'min': 5, 'max': 15, 'step': 5}
    params['parameters']['Cw'] = {'min': 0.005, 'max': 0.03, 'step': 0.005}
    params['parameters']['Cm'] = {'min': 0.005, 'max': 0.015, 'step': 0.005}
    params['parameters']['N'] = {'min': 1.2, 'max': 1.8, 'step': 0.2}
    
    # 设置观测几何（Sentinel-2典型值）
    params['geometry']['solar_zenith'] = 30
    params['geometry']['view_zenith'] = 10
    params['geometry']['azimuth'] = 90
    
    print(f"  参数范围:")
    for param, range_info in params['parameters'].items():
        print(f"    {param}: {range_info['min']} - {range_info['max']}, 步长 {range_info['step']}")
    
    lut_id = engine.build_lut(params)
    print(f"\n  查找表构建完成!")
    print(f"  LUT ID: {lut_id}")
    print(f"  LUT大小: {len(engine.lut)} 个组合")
    
    # 保存查找表
    engine.save_lut(lut_file)
    print(f"  查找表已保存: {lut_file}")

# ============================================================================
# 步骤3: 执行LAI反演
# ============================================================================
print("\n【步骤3】执行LAI反演")
print("-" * 70)

# 创建植被掩膜（NDVI > 0.2）
vegetation_mask = ndvi > 0.2
print(f"  植被掩膜: {np.sum(vegetation_mask)} / {vegetation_mask.size} 像元 ({100*np.sum(vegetation_mask)/vegetation_mask.size:.1f}%)")

# 为了测试，先随机选择100个植被像元进行反演
np.random.seed(42)
veg_indices = np.where(vegetation_mask)
n_samples = min(100, len(veg_indices[0]))
sample_indices = np.random.choice(len(veg_indices[0]), n_samples, replace=False)

print(f"\n  随机选择 {n_samples} 个植被像元进行反演测试...")

lai_results = []
confidence_results = []

for i, idx in enumerate(sample_indices):
    row = veg_indices[0][idx]
    col = veg_indices[1][idx]
    
    reflectance = {
        'B2': float(b2[row, col]),
        'B3': float(b3[row, col]),
        'B4': float(b4[row, col]),
        'B8': float(b8[row, col])
    }
    
    result = engine.invert_lai(reflectance)
    
    lai_results.append({
        'row': row,
        'col': col,
        'lat': transform.c + col * transform.a,
        'lon': transform.f + row * transform.e,
        'B2': reflectance['B2'],
        'B3': reflectance['B3'],
        'B4': reflectance['B4'],
        'B8': reflectance['B8'],
        'NDVI': ndvi[row, col],
        'LAI': result['LAI'],
        'confidence': result['confidence'],
        'Cab': result['parameters']['Cab'],
        'Car': result['parameters']['Car']
    })
    
    if (i + 1) % 20 == 0:
        print(f"    已处理 {i+1}/{n_samples} 像元")

# 转换为DataFrame
df_results = pd.DataFrame(lai_results)

print(f"\n  反演结果统计:")
print(f"    LAI最小值: {df_results['LAI'].min():.2f}")
print(f"    LAI最大值: {df_results['LAI'].max():.2f}")
print(f"    LAI平均值: {df_results['LAI'].mean():.2f}")
print(f"    LAI标准差: {df_results['LAI'].std():.2f}")
print(f"    平均置信度: {df_results['confidence'].mean():.3f}")

# 显示前10个结果
print(f"\n  前10个反演结果:")
for i in range(min(10, len(df_results))):
    r = df_results.iloc[i]
    print(f"    点{i+1}: 位置({r['row']},{r['col']}) NDVI={r['NDVI']:.3f} -> LAI={r['LAI']:.2f}")

# ============================================================================
# 步骤4: 精度验证
# ============================================================================
print("\n【步骤4】精度验证")
print("-" * 70)

# 将地面实测点坐标转换为图像行列号
# 注意：这里简化处理，假设测量点在图像范围内
print("  匹配地面实测点与反演结果...")

matched_results = []

for idx, row in df_measured.iterrows():
    lat, lon = row['纬度'], row['经度']
    
    # 计算行列号
    col = int((lon - transform.c) / transform.a)
    row_idx = int((lat - transform.f) / transform.e)
    
    # 检查是否在图像范围内
    if 0 <= col < img.shape[2] and 0 <= row_idx < img.shape[1]:
        # 检查是否为植被像元
        if vegetation_mask[row_idx, col]:
            reflectance = {
                'B2': float(b2[row_idx, col]),
                'B3': float(b3[row_idx, col]),
                'B4': float(b4[row_idx, col]),
                'B8': float(b8[row_idx, col])
            }
            
            result = engine.invert_lai(reflectance)
            
            matched_results.append({
                'measured_lai': row['LAI'],
                'predicted_lai': result['LAI'],
                'confidence': result['confidence'],
                'lat': lat,
                'lon': lon,
                'row': row_idx,
                'col': col,
                'NDVI': ndvi[row_idx, col]
            })

print(f"  成功匹配 {len(matched_results)} 个点")

if len(matched_results) > 0:
    df_matched = pd.DataFrame(matched_results)
    
    # 计算精度指标
    measured = df_matched['measured_lai'].values
    predicted = df_matched['predicted_lai'].values
    
    mae = np.mean(np.abs(predicted - measured))
    rmse = np.sqrt(np.mean((predicted - measured) ** 2))
    bias = np.mean(predicted - measured)
    
    # 计算R²
    ss_res = np.sum((measured - predicted) ** 2)
    ss_tot = np.sum((measured - np.mean(measured)) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    
    print(f"\n  精度指标:")
    print(f"    样本数: {len(matched_results)}")
    print(f"    平均绝对误差 (MAE): {mae:.3f}")
    print(f"    均方根误差 (RMSE): {rmse:.3f}")
    print(f"    偏差 (Bias): {bias:.3f}")
    print(f"    决定系数 (R²): {r2:.3f}")
    
    # 显示对比
    print(f"\n  实测 vs 反演对比 (前10个):")
    for i in range(min(10, len(df_matched))):
        r = df_matched.iloc[i]
        diff = abs(r['predicted_lai'] - r['measured_lai'])
        print(f"    点{i+1}: 实测={r['measured_lai']:.2f}, 反演={r['predicted_lai']:.2f}, "
              f"差值={diff:.2f}, NDVI={r['NDVI']:.3f}")
    
    # 保存匹配结果
    df_matched.to_csv('lai_validation_results.csv', index=False)
    print(f"\n  验证结果已保存: lai_validation_results.csv")
else:
    print("  警告: 未能匹配到有效的地面实测点")

# ============================================================================
# 步骤5: 保存反演结果
# ============================================================================
print("\n【步骤5】保存反演结果")
print("-" * 70)

# 保存样本反演结果
df_results.to_csv('lai_inversion_samples.csv', index=False)
print(f"  样本反演结果已保存: lai_inversion_samples.csv ({len(df_results)} 条记录)")

# 创建全图LAI反演结果（简化版，仅测试区域）
print(f"\n  创建LAI反演结果图...")

lai_map = np.zeros_like(b2)
lai_map.fill(np.nan)

for _, r in df_results.iterrows():
    lai_map[int(r['row']), int(r['col'])] = r['LAI']

# 保存为GeoTIFF
output_profile = profile.copy()
output_profile.update({
    'dtype': 'float32',
    'count': 1,
    'nodata': np.nan
})

with rasterio.open('lai_inversion_result.tif', 'w', **output_profile) as dst:
    dst.write(lai_map.astype(np.float32), 1)

print(f"  LAI反演结果图已保存: lai_inversion_result.tif")

# ============================================================================
# 完成
# ============================================================================
print("\n" + "=" * 70)
print("LAI反演完成!")
print("=" * 70)
print(f"\n输出文件:")
print(f"  1. lai_inversion_samples.csv - 样本反演结果")
print(f"  2. lai_validation_results.csv - 精度验证结果")
print(f"  3. lai_inversion_result.tif - LAI空间分布图")
print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
