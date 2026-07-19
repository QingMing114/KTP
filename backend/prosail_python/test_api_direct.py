#!/usr/bin/env python3
"""
直接测试FastAPI应用，不通过HTTP
"""

import sys
sys.path.append('.')

from fastapi_app import app, engine
from fastapi.testclient import TestClient

print("直接测试FastAPI应用...")
print("=" * 50)

# 创建测试客户端
client = TestClient(app)

# 1. 测试根端点
print("\n1. 测试根端点 /")
response = client.get("/")
print(f"   状态码: {response.status_code}")
if response.status_code == 200:
    print(f"   响应: {response.json()}")

# 2. 测试状态端点
print("\n2. 测试状态端点 /api/status")
response = client.get("/api/status")
print(f"   状态码: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   LUT加载: {data.get('lut_loaded')}")
    print(f"   LUT大小: {data.get('lut_size')}")

# 3. 构建默认查找表
print("\n3. 构建默认查找表 /api/lut/default")
response = client.post("/api/lut/default")
print(f"   状态码: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"   响应: {result}")
else:
    print(f"   错误: {response.text}")

# 4. 再次检查状态
print("\n4. 再次检查状态")
response = client.get("/api/status")
if response.status_code == 200:
    data = response.json()
    print(f"   LUT加载: {data.get('lut_loaded')}")
    print(f"   LUT大小: {data.get('lut_size')}")

# 5. 测试LAI反演
print("\n5. 测试LAI反演 /api/inversion/lai")
response = client.post(
    "/api/inversion/lai",
    json={
        "reflectance": {
            "B2": 0.05,
            "B3": 0.08,
            "B4": 0.04,
            "B8": 0.35
        },
        "method": "min_distance"
    }
)
print(f"   状态码: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"   LAI: {result.get('LAI')}")
    print(f"   置信度: {result.get('confidence')}")
    print(f"   参数: {result.get('parameters')}")
else:
    print(f"   错误: {response.text}")

print("\n" + "=" * 50)
print("测试完成!")
