import pandas as pd

# 验证结果文件
df = pd.read_csv('lai_validation_results_v2.csv')
print('验证结果文件:')
print(f"  记录数: {len(df)}")
print(f"  列: {df.columns.tolist()}")
print(f"  实测LAI范围: [{df['measured_lai'].min():.2f}, {df['measured_lai'].max():.2f}]")
print(f"  反演LAI范围: [{df['predicted_lai'].min():.2f}, {df['predicted_lai'].max():.2f}]")
print(f"  平均NDVI: {df['NDVI'].mean():.3f}")
print()
print('前5行:')
print(df.head())
