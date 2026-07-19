from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
import numpy as np
import uvicorn
import os
from prosail_api import PROSAILEngine, create_default_params

app = FastAPI(
    title="PROSAIL LAI Inversion API",
    description="API for LAI inversion using PROSAIL radiative transfer model",
    version="1.0.0"
)

engine = PROSAILEngine()

class LUTBuildRequest(BaseModel):
    parameters: Dict
    geometry: Dict
    soil: Dict
    bands: Optional[List[float]] = [490, 560, 665, 842]

class InversionRequest(BaseModel):
    lut_id: Optional[str] = None
    reflectance: Dict
    method: str = "min_distance"
    options: Optional[Dict] = None

class BatchInversionRequest(BaseModel):
    lut_id: Optional[str] = None
    reflectance_data: List[List[float]]
    method: str = "min_distance"
    options: Optional[Dict] = None

@app.get("/")
async def root():
    return {
        "message": "PROSAIL LAI Inversion API",
        "version": "1.0.0",
        "endpoints": {
            "/api/lut/build": "POST - Build lookup table",
            "/api/lut/load": "POST - Load existing lookup table",
            "/api/lut/save": "POST - Save lookup table",
            "/api/inversion/lai": "POST - Invert LAI for single pixel",
            "/api/inversion/batch": "POST - Batch LAI inversion",
            "/api/status": "GET - Get engine status"
        }
    }

@app.get("/api/status")
async def get_status():
    return {
        "lut_loaded": engine.lut is not None,
        "lut_id": engine.lut_id,
        "lut_size": len(engine.lut) if engine.lut is not None else 0
    }

@app.post("/api/lut/build")
async def build_lut(request: LUTBuildRequest, background_tasks: BackgroundTasks):
    try:
        params = {
            'parameters': request.parameters,
            'geometry': request.geometry,
            'soil': request.soil,
            'bands': request.bands
        }
        
        lut_id = engine.build_lut(params)
        
        return {
            "status": "success",
            "lut_id": lut_id,
            "size": len(engine.lut),
            "parameters": params
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/lut/save")
async def save_lut(filepath: str):
    try:
        engine.save_lut(filepath)
        return {
            "status": "success",
            "message": f"LUT saved to {filepath}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/lut/load")
async def load_lut(filepath: str):
    try:
        engine.load_lut(filepath)
        return {
            "status": "success",
            "lut_id": engine.lut_id,
            "size": len(engine.lut)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inversion/lai")
async def invert_lai(request: InversionRequest):
    try:
        if engine.lut is None:
            raise HTTPException(
                status_code=400, 
                detail="LUT not built or loaded. Please build or load a LUT first."
            )
        
        result = engine.invert_lai(
            reflectance=request.reflectance,
            method=request.method,
            options=request.options
        )
        
        return {
            "status": "success",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/inversion/batch")
async def batch_invert(request: BatchInversionRequest):
    try:
        if engine.lut is None:
            raise HTTPException(
                status_code=400,
                detail="LUT not built or loaded. Please build or load a LUT first."
            )
        
        reflectance_array = np.array(request.reflectance_data)
        LAI_results, confidence_results = engine.batch_invert(
            reflectance_array=reflectance_array,
            method=request.method,
            options=request.options
        )
        
        return {
            "status": "success",
            "LAI_results": LAI_results.tolist(),
            "confidence_results": confidence_results.tolist(),
            "n_pixels": len(LAI_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/lut/default")
async def build_default_lut():
    try:
        params = create_default_params()
        lut_id = engine.build_lut(params)
        
        return {
            "status": "success",
            "lut_id": lut_id,
            "size": len(engine.lut),
            "message": "Default LUT built successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
