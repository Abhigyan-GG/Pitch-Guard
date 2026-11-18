"""Start the local application. Bind only to this computer by default."""
import os
from pathlib import Path

if __name__=='__main__':
    os.environ.setdefault('YOLO_CONFIG_DIR',str(Path(__file__).resolve().parent/'.runtime/ultralytics'))
    import uvicorn
    uvicorn.run('src.server:app',host='127.0.0.1',port=int(os.environ.get('PITCHGUARD_PORT','8000')))
