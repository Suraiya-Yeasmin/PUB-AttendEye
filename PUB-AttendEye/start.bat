@echo off
cd /d %~dp0
if not exist .venv ( python -m venv .venv && call .venv\Scripts\activate.bat && pip install -r requirements.txt ) else ( call .venv\Scripts\activate.bat )
if not exist models\face_recognition_sface_2021dec.onnx python scripts\download_models.py
python run.py
pause
