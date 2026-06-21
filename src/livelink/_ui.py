"""Default browser audio client for agent.serve().

Provides a minimal but functional voice UI that works out of the box.
Uses ScriptProcessor for maximum browser compatibility.
"""

from __future__ import annotations

DEFAULT_HTML = """<!DOCTYPE html>
<html><head><title>LiveLink Voice Agent</title></head>
<body style="font-family:system-ui,sans-serif;max-width:600px;margin:40px auto;padding:20px">
<h1>Voice Agent</h1>
<p>Click Start and speak naturally. The agent will respond with voice.</p>
<button id="start" style="font-size:18px;padding:10px 24px;cursor:pointer">Start</button>
<button id="stop" style="font-size:18px;padding:10px 24px;cursor:pointer" disabled>Stop</button>
<div id="status" style="margin-top:20px;color:#666;min-height:24px"></div>
<div id="transcript" style="margin-top:16px;padding:12px;background:#f5f5f5;border-radius:8px;min-height:60px;white-space:pre-wrap;font-size:14px;display:none"></div>
<script>
let ws, audioCtx, mediaStream, processor, playbackQueue = [], isPlaying = false;
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
const WS_URL = `ws://${location.host}/ws`;

document.getElementById('start').onclick = async () => {
    document.getElementById('start').disabled = true;
    document.getElementById('stop').disabled = false;
    status.textContent = 'Connecting...';

    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = async () => {
        status.textContent = 'Listening...';
        audioCtx = new AudioContext({sampleRate: 16000});
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {sampleRate: 16000, channelCount: 1, echoCancellation: true}
        });
        const src = audioCtx.createMediaStreamSource(mediaStream);
        processor = audioCtx.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
            if (ws.readyState !== 1) return;
            const f = e.inputBuffer.getChannelData(0);
            let sumSq = 0;
            for (let i = 0; i < f.length; i++) sumSq += f[i] * f[i];
            if (Math.sqrt(sumSq / f.length) < 0.008) return;
            const i16 = new Int16Array(f.length);
            for (let i = 0; i < f.length; i++)
                i16[i] = Math.max(-32768, Math.min(32767, f[i] * 32768));
            ws.send(i16.buffer);
        };
        src.connect(processor);
        processor.connect(audioCtx.destination);
    };

    ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
            playbackQueue.push(e.data);
            if (!isPlaying) playNext();
        } else {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'text') {
                    transcript.style.display = 'block';
                    transcript.textContent += msg.text;
                } else if (msg.type === 'turn_complete') {
                    transcript.textContent += '\\n';
                }
            } catch(err) {}
        }
    };

    ws.onclose = () => {
        status.textContent = 'Disconnected';
        cleanup();
    };
    ws.onerror = () => {
        status.textContent = 'Connection error';
        cleanup();
    };
};

document.getElementById('stop').onclick = () => { if (ws) ws.close(); cleanup(); };

function cleanup() {
    document.getElementById('start').disabled = false;
    document.getElementById('stop').disabled = true;
    if (processor) processor.disconnect();
    if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    playbackQueue = [];
    isPlaying = false;
}

function playNext() {
    if (playbackQueue.length === 0) { isPlaying = false; return; }
    isPlaying = true;
    const buf = playbackQueue.shift();
    const ctx = new AudioContext({sampleRate: 24000});
    const i16 = new Int16Array(buf);
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const ab = ctx.createBuffer(1, f32.length, 24000);
    ab.getChannelData(0).set(f32);
    const s = ctx.createBufferSource();
    s.buffer = ab;
    s.connect(ctx.destination);
    s.onended = () => playNext();
    s.start();
}
</script>
</body></html>"""
