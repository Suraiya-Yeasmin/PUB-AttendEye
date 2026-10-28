// Webcam helper (browser getUserMedia). Frames are captured as JPEG and sent to the backend CV service.
export const CAM_KEY = 'attendeye.cameraId';
export const savedCamera = () => { try { return localStorage.getItem(CAM_KEY) || ''; } catch { return ''; } };
export const saveCamera = (id) => { try { localStorage.setItem(CAM_KEY, id); } catch {} };

export function describeCameraError(err) {
  switch (err && err.name) {
    case 'NotAllowedError': case 'SecurityError': return 'Camera permission was denied. Allow camera access for this site in the browser address bar, then press Start Camera again.';
    case 'NotFoundError': case 'OverconstrainedError': return 'No usable camera was found. Connect a webcam (or choose a different camera in Settings) and try again.';
    case 'NotReadableError': case 'AbortError': return 'The camera is in use by another application or could not be opened. Close other apps using the camera and try again.';
    default: return `Could not start the camera: ${err?.message || 'unknown error'}.`;
  }
}
export async function listCameras() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try { return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput'); } catch { return []; }
}

export class Camera {
  constructor(video) { this.video = video; this.stream = null; this.canvas = document.createElement('canvas'); }
  get running() { return !!this.stream; }
  async start(deviceId = savedCamera()) {
    if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('This browser does not support camera access (use Chrome or Edge on http://localhost).'), { name: 'NotFoundError' });
    const video = { width: { ideal: 1280 }, height: { ideal: 720 } };
    if (deviceId) video.deviceId = { exact: deviceId };
    try { this.stream = await navigator.mediaDevices.getUserMedia({ video, audio: false }); }
    catch (e) { if (deviceId && e.name === 'OverconstrainedError') { delete video.deviceId; this.stream = await navigator.mediaDevices.getUserMedia({ video, audio: false }); } else throw e; }
    this.video.srcObject = this.stream;
    await this.video.play();
    this.stream.getVideoTracks()[0].addEventListener('ended', () => this.onEnded?.());
    return this.stream.getVideoTracks()[0].label;
  }
  stop() { this.stream?.getTracks().forEach((t) => t.stop()); this.stream = null; this.video.srcObject = null; }
  // Returns a JPEG blob no wider than maxW (keeps uploads small and the CV workload predictable).
  capture(maxW = 640, quality = 0.85) {
    const v = this.video; if (!v.videoWidth) return Promise.resolve(null);
    const s = Math.min(1, maxW / v.videoWidth);
    this.canvas.width = Math.round(v.videoWidth * s); this.canvas.height = Math.round(v.videoHeight * s);
    this.canvas.getContext('2d').drawImage(v, 0, 0, this.canvas.width, this.canvas.height);
    return new Promise((res) => this.canvas.toBlob(res, 'image/jpeg', quality));
  }
}

// Draws boxes/labels on an overlay canvas that sits above a mirrored <video>. Coordinates are mirrored to match.
export function drawFaces(canvas, video, frame, faces) {
  const W = canvas.clientWidth, H = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
  if (canvas.width !== W * dpr || canvas.height !== H * dpr) { canvas.width = W * dpr; canvas.height = H * dpr; }
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  if (!frame || !faces?.length) return;
  // The video uses object-fit: contain; compute the displayed rectangle.
  const vr = frame.w / frame.h, cr = W / H;
  const dw = vr > cr ? W : H * vr, dh = vr > cr ? W / vr : H, ox = (W - dw) / 2, oy = (H - dh) / 2, sx = dw / frame.w, sy = dh / frame.h;
  for (const f of faces) {
    const b = f.bbox; const w = b.w * sx, hh = b.h * sy; const x = ox + dw - (b.x * sx + w), y = oy + b.y * sy; // mirrored
    ctx.lineWidth = 3; ctx.strokeStyle = f.color; ctx.strokeRect(x, y, w, hh);
    const lines = f.lines || []; ctx.font = '600 13px "Segoe UI", system-ui, sans-serif';
    const tw = Math.max(...lines.map((l) => ctx.measureText(l).width), 40) + 16, th = lines.length * 18 + 10;
    let ly = y - th - 4; if (ly < 2) ly = y + hh + 4;
    let lx = Math.min(Math.max(x, 2), W - tw - 2);
    ctx.fillStyle = f.color; ctx.beginPath(); ctx.roundRect(lx, ly, tw, th, 7); ctx.fill();
    ctx.fillStyle = '#fff'; lines.forEach((l, i) => ctx.fillText(l, lx + 8, ly + 18 + i * 18 - 3));
  }
}
