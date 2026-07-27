"""Launch the V1 CAD-BOM input-layer app."""
import uvicorn

from backend import config

if __name__ == "__main__":
    print(f"CAD-BOM V1 input layer -> http://127.0.0.1:{config.PORT}")
    print(f"  model={config.EXTRACTION_MODEL}  api_key={'set' if config.has_api_key() else 'MISSING'}")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=config.PORT, reload=False)
