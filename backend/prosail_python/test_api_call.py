#!/usr/bin/env python3
"""
测试API调用 - 使用TestClient直接测试FastAPI应用
"""

import sys
sys.path.append('.')

from fastapi.testclient import TestClient
from fastapi_app import app

# 创建测试客户端
client = TestClient(app)

print("=" * 60)
print("测试PROSAIL API调用")
print("=" * 60)

# 测试1: 查看API信息
print("\n【测试1】获取API信息")
response = client.get("/")
print(f"状态码: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"API名称: {data.get('message')}")
    print(f"版本: {data.get('version')}")
    print("可用端点:")
    for endpoint, desc in data.get('endpoints', {}).items():
        print(f"  {endpoint}: {desc}")

# 测试2: 检查状态
print("\n【测试2】检查API状态")
response = client.get("/api/status")
print(f"状态码: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"LUT已加载: {data.get('lut_loaded')}")
    print(f"LUT大小: {data.get('lut_size')}")

# 测试3: 构建查找表
print("\n【测试3】构建默认查找表")
print("正在构建，请稍候...")
response = client.post("/api/lut/default")
print(f"状态码: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"状态: {data.get('status')}")
    print(f"LUT ID: {data.get('lut_id')}")
    print(f"LUT大小: {data.get('size')}")
    print(f"消息: {data.get('message')}")
else:
    print(f"错误: {response.text}")

# 测试4: LAI反演
print("\n【测试4】LAI反演")
test_cases = [
    {"B2": 0.05, "B3": 0.08, "B4": 0.04, "B8": 0.35},
    {"B2": 0.03, "B3": 0.05, "B4": 0.02, "B8": 0.25},
    {"B2": 0.08, "B3": 0.12, "B4": 0.06, "B8": 0.45},
]

for i, reflectance in enumerate(test_cases, 1):
    print(f"\n  测试用例{i}: {reflectance}")
    response = client.post(
        "/api/inversion/lai",
        json={
            "reflectance": reflectance,
            "method": "min_distance"
        }
    )
    print(f"  状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"  LAI: {result.get('LAI'):.2f}")
        print(f"  置信度: {result.get('confidence'):.3f}")
        params = result.get('parameters', {})
        print(f"  参数: Cab={params.get('Cab')}, Car={params.get('Car')}, N={params.get('N')}")
    else:
        print(f"  错误: {response.text}")

# 测试5: 批量反演
print("\n【测试5】批量LAI反演")
batch_data = [
    [0.05, 0.08, 0.04, 0.35],
    [0.03, 0.05, 0.02, 0.25],
    [0.08, 0.12, 0.06, 0.45],
]
response = client.post(
    "/api/inversion/batch",
    json={
        "reflectance_data": batch_data,
        "method": "min_distance"
    }
)
print(f"状态码: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"状态: {result.get('status')}")
    print(f"反演像素数: {result.get('n_pixels')}")
    lai_results = result.get('LAI_results', [])
    print(f"LAI结果: {[f'{x:.2f}' for x in lai_results]}")
else:
    print(f"错误: {response.text}")

print("\n" + "=" * 60)
print("API调用测试完成!")
print("=" * 60)
