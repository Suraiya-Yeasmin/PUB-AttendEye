# Third-party models and licences

| Component | Source | Licence (from the repository's own LICENSE file) |
|---|---|---|
| YuNet face detector `face_detection_yunet_2023mar.onnx` | OpenCV Zoo, from ShiqiYu/libfacedetection.train | MIT |
| SFace face recogniser `face_recognition_sface_2021dec.onnx` | OpenCV Zoo (MobileFaceNet trained with the SFace loss) | Apache 2.0 |
| OpenCV, FastAPI, SQLAlchemy, NumPy, cryptography, Uvicorn | PyPI | Apache 2.0 / BSD / MIT (see each package) |

- Models are **not** committed. `python scripts/download_models.py` downloads them and verifies SHA-256 checksums.
- Both licences permit the use in this project. **Not verified by us:** the licences/terms of the datasets the models were trained on. If you present or deploy beyond a student competition, check the SFace paper (arXiv 2205.12010) and the OpenCV Zoo README, and obtain legal advice.
- This is not legal advice and makes no claim of compliance with any privacy law.
