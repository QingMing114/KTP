import sys
sys.path.append('.')

import numpy as np
import rasterio
import pandas as pd
from prosail_api import PROSAILEngine, create_default_params

print("=" * 60)
print("使用真实数据进行PROSAIL LAI反演测试")
print("=" * 60)

print("\n1. 读取预处理后的卫星数据...")
try:
    with rasterio.open('../04中间产品（预处理）/张掖/zhangye.tif') as src:
        img = src.read()
        transform = src.transform
        crs = src.crs
        print(f"   图像形状: {img.shape}")
        print(f"   像素大小: {src.res}")
        print(f"   数据类型: {src.dtypes[0]}")
except Exception as e:
    print(f"   读取失败: {e}")
    sys.exit(1)

print("\n2. 读取地面实测LAI数据...")
try:
    df_measured = pd.read_excel('../02地面测量数据/张掖/LAI2200/张掖.xlsx')
    print(f"   实测数据形状: {df_measured.shape}")
    print(f"   列名: {df_measured.columns.tolist()}")
    print(f"   前5行:\n{df_measured.head()}")
except Exception as e:
    print(f"   读取失败: {e}")
    sys.exit(1)

print("\n3. 构建查找表...")
engine = PROSAILEngine()

params = create_default_params()
params['bands'] = [490, 560, 665, 842]
params['parameters']['LAI'] = {'min': 0, 'max': 6, 'step': 0.5}
params['parameters']['Cab'] = {'min': 20, 'max': 80, 'step': 10}
params['parameters']['Car'] = {'min': 5, 'max': 15, 'step': 5}
params['parameters']['Cw'] = {'min': 0.005, 'max': 0.03, 'step': 0.005}
params['parameters']['Cm'] = {'min': 0.005, 'max': 0.015, 'step': 0.005}
params['parameters']['N'] = {'min': 1.2, 'max': 1.8, 'step': 0.2}

lut_id = engine.build_lut(params)
print(f"   查找表构建完成! ID: {lut_id}")
print(f"   查找表大小: {len(engine.lut)}")

engine.save_lut("zhangye_lut.pkl")
print("   查找表已保存")

print("\n4. 读取卫星反射率...")
bands_info = [
    (490, 'B2', '蓝光'),
    (560, 'B3', '绿光'),
    (665, 'B4', '红光'),
    (842, 'B8', '近红外')
]

band_reflectance = {}
for wl, band_name, desc in bands_info:
    band_data = img[img.shape[0] - 1 - list(range(img.shape[0]))[::-1].index(0) if wl == 490 else 0]
    band_reflectance[band_name] = img[0].astype(float) / 10000.0 if img[0].max() > 1 else img[0].astype(float)
    print(f"   {band_name} ({desc}, {wl}nm): min={band_reflectance[band_name].min():.4f}, max={band_reflectance[band_name].max():.4f}")

print("\n5. 选择测试点进行LAI反演...")
sample_pixels = []
for idx, row in df_measured.iterrows():
    if idx >= 5:
        break
    if 'X' in df_measured.columns and 'Y' in df_measured.columns:
        x, y = row['X'], row['Y']
        try:
            col = int((x - transform.c) / transform.a)
            row_idx = int((y - transform.f) / transform.e)
            if 0 <= col < img.shape[2] and 0 <= row_idx < img.shape[1]:
                reflectance = {
                    'B2': float(img[0, row_idx, col]) / 10000.0 if img[0].max() > 1 else float(img[0, row_idx, col]),
                    'B3': float(img[1, row_idx, col]) / 10000.0 if img[1].max() > 1 else float(img[1, row_idx, col]),
                    'B4': float(img[2, row_idx, col]) / 10000.0 if img[2].max() > 1 else float(img[2, row_idx, col]),
                    'B8': float(img[3, row_idx, col]) / 10000.0 if img[3].max() > 1 else float(img[3, row_idx, col])
                }
                sample_pixels.append({
                    'row': row_idx,
                    'col': col,
                    'reflectance': reflectance,
                    'measured_lai': row.get('LAI', None)
                })
                print(f"   点{idx+1}: 行={row_idx}, 列={col}, 实测LAI={row.get('LAI', 'N/A')}")
        except:
            pass

print(f"\n6. 反演测试 (共{len(sample_pixels)}个样本点)...")
predicted_lai = []
measured_lai = []

for i, pixel in enumerate(sample_pixels):
    result = engine.invert_lai(pixel['reflectance'])
    predicted_lai.append(result['LAI'])
    measured_lai.append(pixel['measured_lai'])
    print(f"   点{i+1}: 实测LAI={pixel['measured_lai']:.2f}, 反演LAI={result['LAI']:.2f}, 置信度={result['confidence']:.2f}")

print("\n7. 精度验证...")
predicted_lai = np.array(predicted_lai)
measured_lai = np.array([m for m in measured_lai if m is not None])

if len(predicted_lai) > 0 and len(measured_lai) > 0:
    min_len = min(len(predicted_lai), len(measured_lai))
    pred = predicted_lai[:min_len]
    meas = measured_lai[:min_len]
    
    mae = np.mean(np.abs(pred - meas))
    rmse = np.sqrt(np.mean((pred - meas) ** 2))
    
    correlation = np.corrcoef(pred, meas)[0, 1]
    
    print(f"   平均绝对误差 (MAE): {mae:.3f}")
    print(f"   均方根误差 (RMSE): {rmse:.3f}")
    print(f"   相关系数 (R): {correlation:.3f}")
else:
    print("   警告: 缺少有效的测量数据进行验证")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)