import sys
sys.path.append('.')

from prosail import prosail
from prospect import data_spec_pdb

print("Testing PROSAIL Python implementation...")

data = data_spec_pdb()
print(f"Spectral data loaded: {data.shape[0]} wavelengths from {data[0,0]}nm to {data[-1,0]}nm")

Rsoil1 = data[:, 10]
Rsoil2 = data[:, 11]
rsoil = Rsoil1

print("\nTesting PROSAIL with default parameters...")
try:
    rdot, rsot, rddt, rsdt = prosail(
        N=1.5,
        Cab=40,
        Car=8,
        Ant=0,
        Cbrown=0,
        Cw=0.01,
        Cm=0.009,
        LIDFa=30,
        LIDFb=0,
        TypeLidf=2,
        lai=5.0,
        q=0.01,
        tts=30,
        tto=10,
        psi=90,
        rsoil=rsoil
    )
    
    print(f"✓ PROSAIL executed successfully!")
    print(f"  rdot shape: {rdot.shape}")
    print(f"  rsot shape: {rsot.shape}")
    
    idx_490 = 90
    idx_665 = 265
    idx_842 = 442
    
    print(f"  Sample reflectance at 490nm: {rsot[idx_490]:.4f}")
    print(f"  Sample reflectance at 665nm: {rsot[idx_665]:.4f}")
    print(f"  Sample reflectance at 842nm: {rsot[idx_842]:.4f}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting PROSAILEngine...")
from prosail_api import PROSAILEngine, create_default_params

engine = PROSAILEngine()

print("Building small test LUT...")
test_params = {
    'parameters': {
        'LAI': {'min': 2, 'max': 4, 'step': 1},
        'Cab': {'min': 30, 'max': 50, 'step': 10},
        'Car': {'min': 5, 'max': 10, 'step': 5},
        'Cw': {'min': 0.01, 'max': 0.02, 'step': 0.01},
        'Cm': {'min': 0.009, 'max': 0.009, 'step': 0.001},
        'N': {'min': 1.5, 'max': 1.5, 'step': 0.5}
    },
    'geometry': {
        'LIDFa': 30,
        'LIDFb': 0,
        'TypeLidf': 2,
        'solar_zenith': 30,
        'view_zenith': 10,
        'azimuth': 90,
        'hotspot': 0.01
    },
    'soil': {
        'type': 'dry'
    },
    'bands': [490, 665, 842]
}

try:
    lut_id = engine.build_lut(test_params)
    print(f"✓ LUT built successfully! ID: {lut_id}")
    print(f"  LUT size: {len(engine.lut)}")
    
    if len(engine.lut) > 0:
        print("\nTesting LAI inversion...")
        test_reflectance = {
            'B2': 0.05,
            'B3': 0.08,
            'B4': 0.04
        }
        
        result = engine.invert_lai(test_reflectance, options={'bands': ['B2', 'B3', 'B4']})
        print(f"✓ Inversion successful!")
        print(f"  LAI: {result['LAI']:.2f}")
        print(f"  Confidence: {result['confidence']:.4f}")
        print(f"  Parameters: {result['parameters']}")
    else:
        print("⚠ LUT is empty, skipping inversion test")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n✓ All tests completed!")