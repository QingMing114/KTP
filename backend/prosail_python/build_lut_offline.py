#!/usr/bin/env python3
"""
离线构建PROSAIL查找表 (LUT)
运行一次，保存到文件，之后重复使用
"""

import sys
sys.path.append('.')

from prosail_api import PROSAILEngine, create_default_params
import argparse

def build_lut_custom(
    output_file="custom_lut.pkl",
    lai_range=(0, 6, 0.5),
    cab_range=(0, 100, 10),
    car_range=(0, 20, 5),
    cw_range=(0.001, 0.05, 0.01),
    cm_range=(0.001, 0.02, 0.005),
    n_range=(1.0, 2.5, 0.5),
    solar_zenith=30,
    view_zenith=10,
    azimuth=90,
    soil_type='dry',
    bands=[490, 560, 665, 842]
):
    """
    自定义参数构建查找表
    
    参数:
        output_file: 输出文件名
        lai_range: (min, max, step) 叶面积指数范围
        cab_range: (min, max, step) 叶绿素含量范围
        car_range: (min, max, step) 类胡萝卜素范围
        cw_range: (min, max, step) 水分含量范围
        cm_range: (min, max, step) 干物质含量范围
        n_range: (min, max, step) 叶结构参数范围
        solar_zenith: 太阳天顶角
        view_zenith: 观测天顶角
        azimuth: 相对方位角
        soil_type: 土壤类型 ('dry' 或 'wet')
        bands: 波段列表 [nm]
    """
    
    # 创建参数配置
    params = {
        'parameters': {
            'LAI': {'min': lai_range[0], 'max': lai_range[1], 'step': lai_range[2]},
            'Cab': {'min': cab_range[0], 'max': cab_range[1], 'step': cab_range[2]},
            'Car': {'min': car_range[0], 'max': car_range[1], 'step': car_range[2]},
            'Cw': {'min': cw_range[0], 'max': cw_range[1], 'step': cw_range[2]},
            'Cm': {'min': cm_range[0], 'max': cm_range[1], 'step': cm_range[2]},
            'N': {'min': n_range[0], 'max': n_range[1], 'step': n_range[2]},
        },
        'geometry': {
            'LIDFa': 30,
            'LIDFb': 0,
            'TypeLidf': 2,
            'solar_zenith': solar_zenith,
            'view_zenith': view_zenith,
            'azimuth': azimuth,
            'hotspot': 0.01
        },
        'soil': {
            'type': soil_type
        },
        'bands': bands
    }
    
    # 计算总组合数
    import numpy as np
    n_lai = len(np.arange(lai_range[0], lai_range[1] + lai_range[2], lai_range[2]))
    n_cab = len(np.arange(cab_range[0], cab_range[1] + cab_range[2], cab_range[2]))
    n_car = len(np.arange(car_range[0], car_range[1] + car_range[2], car_range[2]))
    n_cw = len(np.arange(cw_range[0], cw_range[1] + cw_range[2], cw_range[2]))
    n_cm = len(np.arange(cm_range[0], cm_range[1] + cm_range[2], cm_range[2]))
    n_n = len(np.arange(n_range[0], n_range[1] + n_range[2], n_range[2]))
    
    total = n_lai * n_cab * n_car * n_cw * n_cm * n_n
    
    print("=" * 60)
    print("PROSAIL 查找表离线构建")
    print("=" * 60)
    print(f"\n参数范围:")
    print(f"  LAI: {lai_range[0]} ~ {lai_range[1]}, step={lai_range[2]} ({n_lai} values)")
    print(f"  Cab: {cab_range[0]} ~ {cab_range[1]}, step={cab_range[2]} ({n_cab} values)")
    print(f"  Car: {car_range[0]} ~ {car_range[1]}, step={car_range[2]} ({n_car} values)")
    print(f"  Cw:  {cw_range[0]} ~ {cw_range[1]}, step={cw_range[2]} ({n_cw} values)")
    print(f"  Cm:  {cm_range[0]} ~ {cm_range[1]}, step={cm_range[2]} ({n_cm} values)")
    print(f"  N:   {n_range[0]} ~ {n_range[1]}, step={n_range[2]} ({n_n} values)")
    print(f"\n几何参数:")
    print(f"  太阳天顶角: {solar_zenith}°")
    print(f"  观测天顶角: {view_zenith}°")
    print(f"  相对方位角: {azimuth}°")
    print(f"  土壤类型: {soil_type}")
    print(f"\n波段: {bands} nm")
    print(f"\n总组合数: {total:,}")
    print(f"输出文件: {output_file}")
    print("=" * 60)
    
    # 构建查找表
    engine = PROSAILEngine()
    
    print("\n开始构建查找表...")
    print("(这可能需要几分钟时间)\n")
    
    lut_id = engine.build_lut(params)
    
    print(f"\n查找表构建完成!")
    print(f"LUT ID: {lut_id}")
    print(f"LUT大小: {len(engine.lut):,} 条记录")
    
    # 保存到文件
    engine.save_lut(output_file)
    
    print(f"\n查找表已保存到: {output_file}")
    print("=" * 60)
    
    return output_file


def build_default_lut():
    """构建默认参数的查找表"""
    print("构建默认参数查找表...")
    return build_lut_custom(
        output_file="zhangye_lut_default.pkl",
        lai_range=(0, 6, 0.5),
        cab_range=(0, 100, 10),
        car_range=(0, 20, 5),
        cw_range=(0.001, 0.05, 0.01),
        cm_range=(0.001, 0.02, 0.005),
        n_range=(1.0, 2.5, 0.5),
        solar_zenith=30,
        view_zenith=10,
        azimuth=90,
        soil_type='dry',
        bands=[490, 560, 665, 842]
    )


def build_high_resolution_lut():
    """构建高分辨率查找表（更精细的参数步长）"""
    print("构建高分辨率查找表...")
    return build_lut_custom(
        output_file="zhangye_lut_highres.pkl",
        lai_range=(0, 8, 0.2),      # 更精细的LAI步长
        cab_range=(0, 100, 5),       # 更精细的Cab步长
        car_range=(0, 20, 2),
        cw_range=(0.001, 0.05, 0.005),
        cm_range=(0.001, 0.02, 0.002),
        n_range=(1.0, 3.0, 0.25),
        solar_zenith=30,
        view_zenith=10,
        azimuth=90,
        soil_type='dry',
        bands=[490, 560, 665, 842]
    )


def build_custom_geometry_lut(solar_zenith, view_zenith, azimuth, output_name):
    """构建特定几何条件下的查找表"""
    print(f"构建特定几何条件查找表 (SZA={solar_zenith}, VZA={view_zenith})...")
    return build_lut_custom(
        output_file=f"zhangye_lut_{output_name}.pkl",
        lai_range=(0, 6, 0.5),
        cab_range=(0, 100, 10),
        car_range=(0, 20, 5),
        cw_range=(0.001, 0.05, 0.01),
        cm_range=(0.001, 0.02, 0.005),
        n_range=(1.0, 2.5, 0.5),
        solar_zenith=solar_zenith,
        view_zenith=view_zenith,
        azimuth=azimuth,
        soil_type='dry',
        bands=[490, 560, 665, 842]
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='离线构建PROSAIL查找表')
    parser.add_argument('--mode', choices=['default', 'highres', 'custom', 'geometry'], 
                       default='default', help='构建模式')
    parser.add_argument('--output', type=str, default=None, help='输出文件名')
    parser.add_argument('--solar-zenith', type=float, default=30, help='太阳天顶角')
    parser.add_argument('--view-zenith', type=float, default=10, help='观测天顶角')
    parser.add_argument('--azimuth', type=float, default=90, help='相对方位角')
    
    args = parser.parse_args()
    
    if args.mode == 'default':
        output = args.output or "zhangye_lut_default.pkl"
        build_lut_custom(output_file=output)
    
    elif args.mode == 'highres':
        build_high_resolution_lut()
    
    elif args.mode == 'geometry':
        geo_name = f"sza{int(args.solar_zenith)}_vza{int(args.view_zenith)}"
        build_custom_geometry_lut(
            args.solar_zenith, 
            args.view_zenith, 
            args.azimuth,
            geo_name
        )
    
    else:
        print("请使用 --mode 参数指定构建模式:")
        print("  python build_lut_offline.py --mode default")
        print("  python build_lut_offline.py --mode highres")
        print("  python build_lut_offline.py --mode geometry --solar-zenith 45 --view-zenith 20")
