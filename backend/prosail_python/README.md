# PROSAIL LAI 反演系统 - 操作指南

## 系统概述

本系统是基于 Python 实现的 PROSAIL 辐射传输模型，用于从 Sentinel-2 卫星数据中反演叶面积指数（LAI）。系统包含完整的查找表构建、LAI 反演和精度验证功能。

## 文件结构

```
prosail_python/
├── prosail_core.py          # 核心数学函数（calctav, campbell等）
├── prospect.py              # PROSPECT-D 叶片光学模型
├── prosail.py               # 4SAIL 冠层辐射传输模型
├── prosail_api.py           # API引擎（LUT构建、LAI反演）
├── fastapi_app.py           # FastAPI Web服务
├── spectral_data.npy        # 光谱数据（400-2500nm）
├── build_lut_offline.py     # 离线构建查找表脚本
├── test_api_call.py         # API调用测试脚本
├── test_real_data_v2.py     # 真实数据测试脚本
├── run_lai_inversion.py     # LAI反演主程序
├── demo_lut.pkl             # 示例查找表（85,800条记录）
└── README.md                # 本文件
```

## 快速开始

### 1. 环境准备

确保已安装以下依赖：

```bash
pip install numpy scipy pandas openpyxl fastapi uvicorn rasterio
```

### 2. 离线构建查找表（LUT）

查找表只需要构建一次，之后可重复使用。

#### 方式一：使用默认参数构建

```bash
python build_lut_offline.py --mode default --output my_lut.pkl
```

**默认参数范围：**
- LAI: 0 ~ 6, 步长 0.5 (13个值)
- Cab: 0 ~ 100, 步长 10 (11个值)
- Car: 0 ~ 20, 步长 5 (5个值)
- Cw: 0.001 ~ 0.05, 步长 0.01 (6个值)
- Cm: 0.001 ~ 0.02, 步长 0.005 (5个值)
- N: 1.0 ~ 2.5, 步长 0.5 (4个值)

**总组合数：** 13 × 11 × 5 × 6 × 5 × 4 = **85,800**

#### 方式二：构建高分辨率查找表

```bash
python build_lut_offline.py --mode highres
```

使用更精细的步长，生成更多组合。

#### 方式三：自定义几何条件

```bash
python build_lut_offline.py --mode geometry --solar-zenith 45 --view-zenith 20
```

根据卫星影像的实际观测几何构建查找表。

### 3. 测试 API 调用

#### 方式一：使用 TestClient（推荐，无需启动服务器）

```bash
python test_api_call.py
```

该脚本会测试以下功能：
- 获取API信息
- 检查API状态
- 构建默认查找表
- 单像素LAI反演（3个测试用例）
- 批量LAI反演

#### 方式二：启动 FastAPI 服务器

```bash
# 启动服务器
uvicorn fastapi_app:app --host 0.0.0.0 --port 8000 --reload

# 在浏览器中查看API文档
# http://localhost:8000/docs
```

### 4. 使用查找表进行 LAI 反演

#### Python 代码示例

```python
from prosail_api import PROSAILEngine

# 创建引擎
engine = PROSAILEngine()

# 加载已构建的查找表（不需要重新构建！）
engine.load_lut("my_lut.pkl")

# 单像素LAI反演
reflectance = {
    "B2": 0.05,   # 490nm
    "B3": 0.08,   # 560nm
    "B4": 0.04,   # 665nm
    "B8": 0.35    # 842nm
}

result = engine.invert_lai(reflectance, method="min_distance")
print(f"LAI: {result['LAI']:.2f}")
print(f"置信度: {result['confidence']:.3f}")
print(f"参数: Cab={result['parameters']['Cab']}, N={result['parameters']['N']}")

# 批量反演
import numpy as np
reflectance_array = np.array([
    [0.05, 0.08, 0.04, 0.35],
    [0.03, 0.05, 0.02, 0.25],
    [0.08, 0.12, 0.06, 0.45]
])

lai_results, confidence = engine.batch_invert(reflectance_array)
print(f"LAI结果: {lai_results}")
```

### 5. 处理真实卫星数据

#### 运行完整反演流程

```bash
python run_lai_inversion.py
```

或

```bash
python test_real_data_v2.py
```

#### 输入数据要求

1. **卫星影像**：`zhangye.tif`
   - 预处理后的 Sentinel-2 反射率数据
   - 波段：B2(490nm), B3(560nm), B4(665nm), B8(842nm)
   - 数据类型：uint16，需除以10000转换为反射率
   - 已进行 NDVI 掩膜（NDVI > 0.2）

2. **地面实测数据**：`张掖.xlsx`
   - 包含 LAI 值、纬度、经度
   - 495个实测点位

#### 输出结果

- LAI 反演结果图像（GeoTIFF格式）
- 精度验证报告（MAE、RMSE、R²）
- 实测 vs 反演散点图

## API 端点说明

### 1. 获取API信息

```http
GET /
```

响应：
```json
{
  "message": "PROSAIL LAI Inversion API",
  "version": "1.0.0",
  "endpoints": {...}
}
```

### 2. 检查状态

```http
GET /api/status
```

响应：
```json
{
  "status": "ready",
  "lut_loaded": true,
  "lut_size": 85800
}
```

### 3. 构建默认查找表

```http
POST /api/lut/default
```

响应：
```json
{
  "status": "success",
  "lut_id": "lut_20240101_120000",
  "size": 85800,
  "message": "Default LUT built successfully"
}
```

### 4. 单像素LAI反演

```http
POST /api/inversion/lai
Content-Type: application/json

{
  "reflectance": {
    "B2": 0.05,
    "B3": 0.08,
    "B4": 0.04,
    "B8": 0.35
  },
  "method": "min_distance"
}
```

响应：
```json
{
  "LAI": 1.5,
  "confidence": 0.992,
  "parameters": {
    "Cab": 40.0,
    "Car": 0.0,
    "Cw": 0.021,
    "Cm": 0.006,
    "N": 1.0
  },
  "distance": 0.008
}
```

### 5. 批量LAI反演

```http
POST /api/inversion/batch
Content-Type: application/json

{
  "reflectance_data": [
    [0.05, 0.08, 0.04, 0.35],
    [0.03, 0.05, 0.02, 0.25]
  ],
  "method": "min_distance"
}
```

## 工作原理

### 查找表构建流程

```
1. 定义参数范围（LAI, Cab, Car, Cw, Cm, N）
        ↓
2. 遍历所有参数组合（85,800种）
        ↓
3. 对每个组合运行 PROSAIL 模型 → 模拟反射率光谱
        ↓
4. 提取指定波段（B2, B3, B4, B8）
        ↓
5. 保存到查找表：[LAI, Cab, Car, Cw, Cm, N, R_B2, R_B3, R_B4, R_B8]
```

### LAI反演流程

```
1. 输入：观测反射率 [B2, B3, B4, B8]
        ↓
2. 在查找表中搜索最接近的模拟反射率（最小距离法）
        ↓
3. 输出：对应参数的 LAI 值
```

## 注意事项

1. **查找表只需构建一次**，保存为 `.pkl` 文件后可重复使用
2. **几何参数**（太阳/观测角度）应与卫星影像元数据一致
3. **土壤类型**可选择 'dry' 或 'wet'，或使用自定义光谱
4. **反演速度**：加载查找表后，单像素反演约毫秒级
5. **精度问题**：如果反演结果与实测值有系统偏差，可能需要调整参数范围或构建更高分辨率的查找表

## 常见问题

### Q: 查找表构建需要多长时间？
A: 默认参数（85,800组合）约需 2-5 分钟，取决于CPU性能。

### Q: 可以修改参数范围吗？
A: 可以，编辑 `build_lut_offline.py` 中的参数范围后重新构建。

### Q: 支持哪些卫星数据？
A: 目前针对 Sentinel-2 的 B2, B3, B4, B8 波段优化，可修改波段配置支持其他传感器。

### Q: 反演精度如何？
A: 精度取决于查找表的分辨率和输入数据质量。建议使用高分辨率查找表并进行精度验证。

## 技术参考

- **PROSPECT-D**: 叶片光学特性模型
- **4SAIL**: 冠层辐射传输模型
- **LUT方法**: 查找表反演方法
- **最小距离法**: 在参数空间中搜索最佳匹配

## 作者与版本

- **版本**: 1.0.0
- **创建日期**: 2024
- **基于**: MATLAB PROSAIL 模型转换

---

如有问题，请参考代码注释或查看 `test_api_call.py` 和 `build_lut_offline.py` 中的示例代码。
