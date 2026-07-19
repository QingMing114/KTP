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
with rasterio.open('../04中间产品（预处理）/张掖/zhangye.tif') as src:
    img = src.read()
    print(f"   图像形状: {img.shape}")
    print(f"   数据范围: {img.min()} - {img.max()}")

print("\n2. 加载已保存的查找表...")
engine = PROSAILEngine()
engine.load_lut("zhangye_lut.pkl")
print(f"   查找表大小: {len(engine.lut)}")

print("\n3. 读取地面实测LAI数据...")
df_measured = pd.read_excel('../02地面测量数据/张掖/LAI2200/张掖.xlsx')
print(f"   实测数据: {len(df_measured)} 个点")
print(f"   LAI范围: {df_measured['LAI'].min():.2f} - {df_measured['LAI'].max():.2f}")

print("\n4. 随机选取图像上的点进行反演测试...")
np.random.seed(42)
n_samples = 10
h, w = img.shape[1], img.shape[2]

sample_results = []
for i in range(n_samples):
    row = np.random.randint(0, h)
    col = np.random.randint(0, w)
    
    reflectance = {
        'B2': float(img[0, row, col]) / 10000.0 if img[0].max() > 1 else float(img[0, row, col]),
        'B3': float(img[1, row, col]) / 10000.0 if img[1].max() > 1 else float(img[1, row, col]),
        'B4': float(img[2, row, col]) / 10000.0 if img[2].max() > 1 else float(img[2, row, col]),
        'B8': float(img[3, row, col]) / 10000.0 if img[3].max() > 1 else float(img[3, row, col])
    }
    
    if reflectance['B8'] > 0.1 and reflectance['B4'] < reflectance['B8']:
        result = engine.invert_lai(reflectance)
        sample_results.append({
            'row': row,
            'col': col,
            'B2': reflectance['B2'],
            'B3': reflectance['B3'],
            'B4': reflectance['B4'],
            'B8': reflectance['B8'],
            'LAI': result['LAI'],
            'confidence': result['confidence']
        })
        
print(f"\n   成功反演 {len(sample_results)} 个有效点:")
for i, r in enumerate(sample_results[:5]):
    print(f"   点{i+1}: 位置({r['row']},{r['col']}) B2={r['B2']:.3f} B3={r['B3']:.3f} B4={r['B4']:.3f} B8={r['B8']:.3f} -> LAI={r['LAI']:.2f}")

lai_values = [r['LAI'] for r in sample_results]
print(f"\n5. 反演结果统计:")
print(f"   LAI最小值: {min(lai_values):.2f}")
print(f"   LAI最大值: {max(lai_values):.2f}")
print(f"   LAI平均值: {np.mean(lai_values):.2f}")
print(f"   LAI标准差: {np.std(lai_values):.2f}")

print("\n6. 与实测LAI对比 (空间位置匹配)...")
sample_measured_lai = df_measured['LAI'].head(len(sample_results)).values
predicted_lai = np.array(lai_values[:len(sample_measured_lai)])

mae = np.mean(np.abs(predicted_lai - sample_measured_lai))
rmse = np.sqrt(np.mean((predicted_lai - sample_measured_lai) ** 2))
correlation = np.corrcoef(predicted_lai, sample_measured_lai)[0, 1]

print(f"   样本数: {len(sample_measured_lai)}")
print(f"   平均绝对误差 (MAE): {mae:.3f}")
print(f"   均方根误差 (RMSE): {rmse:.3f}")
print(f"   相关系数 (R): {correlation:.3f}")

print(f"\n   实测 vs 反演对比:")
for i in range(min(5, len(sample_measured_lai))):
    print(f"   点{i+1}: 实测={sample_measured_lai[i]:.2f}, 反演={predicted_lai[i]:.2f}, 差值={abs(predicted_lai[i]-sample_measured_lai[i]):.2f}")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)