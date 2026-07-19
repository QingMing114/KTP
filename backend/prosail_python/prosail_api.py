import numpy as np
from typing import Dict, List, Tuple, Optional
import pickle
from datetime import datetime
import os
from prosail import prosail
from prospect import data_spec_pdb

class PROSAILEngine:
    def __init__(self):
        self.lut = None
        self.lut_params = None
        self.lut_id = None
        self.data = data_spec_pdb()
        self.wavelengths = self.data[:, 0]
        
    def get_band_index(self, wavelength: float) -> int:
        idx = np.argmin(np.abs(self.wavelengths - wavelength))
        return idx
    
    def build_lut(self, params: Dict) -> str:
        param_ranges = params['parameters']
        geometry = params['geometry']
        soil = params['soil']
        bands = params.get('bands', [490, 560, 665, 842])
        
        LAI_range = np.arange(param_ranges['LAI']['min'], 
                             param_ranges['LAI']['max'] + param_ranges['LAI']['step'], 
                             param_ranges['LAI']['step'])
        Cab_range = np.arange(param_ranges['Cab']['min'], 
                             param_ranges['Cab']['max'] + param_ranges['Cab']['step'], 
                             param_ranges['Cab']['step'])
        Car_range = np.arange(param_ranges['Car']['min'], 
                             param_ranges['Car']['max'] + param_ranges['Car']['step'], 
                             param_ranges['Car']['step'])
        Cw_range = np.arange(param_ranges['Cw']['min'], 
                            param_ranges['Cw']['max'] + param_ranges['Cw']['step'], 
                            param_ranges['Cw']['step'])
        Cm_range = np.arange(param_ranges['Cm']['min'], 
                            param_ranges['Cm']['max'] + param_ranges['Cm']['step'], 
                            param_ranges['Cm']['step'])
        N_range = np.arange(param_ranges['N']['min'], 
                           param_ranges['N']['max'] + param_ranges['N']['step'], 
                           param_ranges['N']['step'])
        
        LIDFa = geometry.get('LIDFa', 30)
        LIDFb = geometry.get('LIDFb', 0)
        TypeLidf = geometry.get('TypeLidf', 2)
        tts = geometry.get('solar_zenith', 30)
        tto = geometry.get('view_zenith', 10)
        psi = geometry.get('azimuth', 90)
        hspot = geometry.get('hotspot', 0.01)
        
        psoil = 1 if soil['type'] == 'dry' else 0
        if soil.get('reflectance') is not None:
            rsoil = soil['reflectance']
        else:
            Rsoil1 = self.data[:, 10]
            Rsoil2 = self.data[:, 11]
            rsoil = psoil * Rsoil1 + (1 - psoil) * Rsoil2
        
        lut_data = []
        total = len(LAI_range) * len(Cab_range) * len(Car_range)
        count = 0
        
        for LAI in LAI_range:
            for Cab in Cab_range:
                for Car in Car_range:
                    for Cw in Cw_range:
                        for Cm in Cm_range:
                            for N in N_range:
                                try:
                                    rdot, rsot, rddt, rsdt = prosail(
                                        N, Cab, Car, 0, 0, Cw, Cm,
                                        LIDFa, LIDFb, TypeLidf,
                                        LAI, hspot, tts, tto, psi, rsoil
                                    )
                                    
                                    band_reflectance = []
                                    for band_wl in bands:
                                        idx = self.get_band_index(band_wl)
                                        band_reflectance.append(rsot[idx])
                                    
                                    lut_data.append([LAI, Cab, Car, Cw, Cm, N] + band_reflectance)
                                    count += 1
                                    
                                    if count % 100 == 0:
                                        print(f"Progress: {count}/{total} ({100*count/total:.1f}%)")
                                except Exception as e:
                                    print(f"Error at LAI={LAI}, Cab={Cab}: {e}")
                                    continue
        
        self.lut = np.array(lut_data)
        self.lut_params = params
        self.lut_id = f"lut_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return self.lut_id
    

    
    def save_lut(self, filepath: str):
        if self.lut is None:
            raise ValueError("No LUT to save")
        
        lut_data = {
            'lut': self.lut,
            'params': self.lut_params,
            'lut_id': self.lut_id
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(lut_data, f)
        
        print(f"LUT saved to {filepath}")
    
    def load_lut(self, filepath: str):
        with open(filepath, 'rb') as f:
            lut_data = pickle.load(f)
        
        self.lut = lut_data['lut']
        self.lut_params = lut_data['params']
        self.lut_id = lut_data['lut_id']
        
        print(f"LUT loaded from {filepath}")
        print(f"LUT ID: {self.lut_id}")
        print(f"LUT size: {len(self.lut)}")
    
    def invert_lai(self, reflectance: Dict, method: str = 'min_distance', 
                  options: Optional[Dict] = None) -> Dict:
        if self.lut is None:
            raise ValueError("LUT not built or loaded")
        
        if options is None:
            options = {}
        
        bands = options.get('bands', ['B2', 'B3', 'B4', 'B8'])
        
        n_lut_bands = self.lut.shape[1] - 6
        if len(bands) != n_lut_bands:
            bands = bands[:n_lut_bands]
        
        weights = options.get('weights', [1.0] * len(bands))
        
        obs_spectrum = np.array([reflectance[band] for band in bands])
        weights = np.array(weights)
        
        lut_spectrum = self.lut[:, 6:6+len(bands)]
        
        if method == 'min_distance':
            weighted_diff = (lut_spectrum - obs_spectrum) * weights
            distances = np.sqrt(np.sum(weighted_diff ** 2, axis=1))
            min_idx = np.argmin(distances)
            
            result = {
                'LAI': float(self.lut[min_idx, 0]),
                'confidence': float(1.0 / (1.0 + distances[min_idx])),
                'parameters': {
                    'Cab': float(self.lut[min_idx, 1]),
                    'Car': float(self.lut[min_idx, 2]),
                    'Cw': float(self.lut[min_idx, 3]),
                    'Cm': float(self.lut[min_idx, 4]),
                    'N': float(self.lut[min_idx, 5])
                },
                'distance': float(distances[min_idx])
            }
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return result
    
    def batch_invert(self, reflectance_array: np.ndarray, 
                    method: str = 'min_distance',
                    options: Optional[Dict] = None) -> np.ndarray:
        if self.lut is None:
            raise ValueError("LUT not built or loaded")
        
        n_pixels = reflectance_array.shape[0]
        n_bands = reflectance_array.shape[1]
        
        lut_spectrum = self.lut[:, 6:6+n_bands]
        LAI_results = np.zeros(n_pixels)
        confidence_results = np.zeros(n_pixels)
        
        for i in range(n_pixels):
            obs_spectrum = reflectance_array[i, :]
            distances = np.sqrt(np.sum((lut_spectrum - obs_spectrum) ** 2, axis=1))
            min_idx = np.argmin(distances)
            
            LAI_results[i] = self.lut[min_idx, 0]
            confidence_results[i] = 1.0 / (1.0 + distances[min_idx])
            
            if (i + 1) % 100 == 0:
                print(f"Processed {i+1}/{n_pixels} pixels")
        
        return LAI_results, confidence_results


def create_default_params() -> Dict:
    return {
        'parameters': {
            'LAI': {'min': 0, 'max': 6, 'step': 0.5},
            'Cab': {'min': 0, 'max': 100, 'step': 10},
            'Car': {'min': 0, 'max': 20, 'step': 5},
            'Cw': {'min': 0.001, 'max': 0.05, 'step': 0.01},
            'Cm': {'min': 0.001, 'max': 0.02, 'step': 0.005},
            'N': {'min': 1.0, 'max': 2.5, 'step': 0.5}
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
        'bands': [490, 560, 665, 842]
    }


if __name__ == '__main__':
    engine = PROSAILEngine()
    
    params = create_default_params()
    
    print("Building LUT...")
    lut_id = engine.build_lut(params)
    print(f"LUT built with ID: {lut_id}")
    
    engine.save_lut(f"prosail_lut_{lut_id}.pkl")
    
    test_reflectance = {
        'B2': 0.05,
        'B3': 0.08,
        'B4': 0.04,
        'B8': 0.35
    }
    
    result = engine.invert_lai(test_reflectance)
    print(f"Inversion result: {result}")
