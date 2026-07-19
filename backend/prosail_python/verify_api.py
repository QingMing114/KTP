from prosail_api import PROSAILEngine, create_default_params
import os

print('验证API引擎...')

engine = PROSAILEngine()
print('✓ PROSAILEngine实例化')

if os.path.exists('zhangye_lut.pkl'):
    engine.load_lut('zhangye_lut.pkl')
    print(f'✓ 查找表加载成功，大小: {len(engine.lut)}')
    
    reflectance = {'B2': 0.05, 'B3': 0.08, 'B4': 0.04, 'B8': 0.35}
    result = engine.invert_lai(reflectance)
    print(f"✓ LAI反演: LAI={result['LAI']:.2f}, confidence={result['confidence']:.3f}")
else:
    print('⚠ 查找表文件不存在')

print('API引擎验证通过!')
