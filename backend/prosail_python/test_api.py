import requests
import json

BASE_URL = "http://localhost:8000"

print("测试PROSAIL API...")
print("=" * 50)

# 1. 测试根端点
try:
    response = requests.get(f"{BASE_URL}/", timeout=5)
    print(f"\n1. 根端点: {response.status_code}")
    if response.status_code == 200:
        print(f"   响应: {response.json()}")
except Exception as e:
    print(f"   错误: {e}")

# 2. 测试状态端点
try:
    response = requests.get(f"{BASE_URL}/api/status", timeout=5)
    print(f"\n2. 状态端点: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"   LUT加载: {data.get('lut_loaded')}")
        print(f"   LUT大小: {data.get('lut_size')}")
except Exception as e:
    print(f"   错误: {e}")

# 3. 构建默认查找表
print(f"\n3. 构建默认查找表...")
try:
    response = requests.post(f"{BASE_URL}/api/lut/default", timeout=300)
    print(f"   状态: {response.status_code}")
    if response.status_code == 200:
        print(f"   响应: {response.json()}")
    else:
        print(f"   错误: {response.text}")
except Exception as e:
    print(f"   错误: {e}")

# 4. 测试LAI反演
print(f"\n4. 测试LAI反演...")
try:
    response = requests.post(
        f"{BASE_URL}/api/inversion/lai",
        json={
            "reflectance": {
                "B2": 0.05,
                "B3": 0.08,
                "B4": 0.04,
                "B8": 0.35
            },
            "method": "min_distance"
        },
        timeout=10
    )
    print(f"   状态: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"   LAI: {result.get('LAI')}")
        print(f"   置信度: {result.get('confidence')}")
    else:
        print(f"   错误: {response.text}")
except Exception as e:
    print(f"   错误: {e}")

print("\n" + "=" * 50)
print("测试完成!")
