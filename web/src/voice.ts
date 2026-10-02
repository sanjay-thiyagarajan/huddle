/** Record from the microphone and return a 16 kHz mono WAV, encoded here so the server needs no ffmpeg. */
export async function recordWav(ms: number): Promise<Blob> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const rec = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => chunks.push(e.data);
  const stopped = new Promise<void>((resolve) => { rec.onstop = () => resolve(); });
  rec.start();
  setTimeout(() => rec.stop(), ms);
  await stopped;
  stream.getTracks().forEach((t) => t.stop());

  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await new Blob(chunks).arrayBuffer());
  await ctx.close();
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * 16000)), 16000);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  return encodeWav((await off.startRendering()).getChannelData(0), 16000);
}

function encodeWav(samples: Float32Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVEfmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 0x7fff, true));
  return new Blob([buf], { type: "audio/wav" });
}

async function send<T>(url: string, wav: Blob): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.message ?? "Voice request failed.");
  return body as T;
}

export const enrolVoice = (name: string, wav: Blob) =>
  send<{ clips: number }>(`/api/voice/enrol?name=${encodeURIComponent(name)}`, wav);
export const identifyVoice = (wav: Blob) =>
  send<{ recognized: boolean; name: string | null; score: number }>("/api/voice/identify", wav);
export const transcribeVoice = (wav: Blob) => send<{ text: string }>("/api/voice/transcribe", wav);

export const ENROL_PHRASES = [
  "Alexa, plan our Saturday.",
  "This is my voice, and I would like to set up my profile.",
  "I can do about ten hours a week.",
];
