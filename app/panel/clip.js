/*  clip.js -- turns a list of timed JPEG frames into a WebM video (2026-10-11).

    Owner: "I want clips of how the person was banned".

    The frames are the ones the client already captured (the rolling buffer
    before a ban, plus the fresh ones after it). Each is drawn on a canvas and
    encoded with WebCodecs' VideoEncoder (VP8, software -- nothing new for the
    GPU process to do), at its real timestamp, then written into a minimal
    WebM container below. Discord plays WebM inline.

    NexusClip.encode(frames, opts) -> Promise<'data:video/webm;base64,...'>
      frames: [{ t: ms, data: 'data:image/jpeg;base64,...' }] (any order)
      opts:   { bitrate, maxWidth }
*/

(function () {
    // ------------------------------------------------------------- EBML writer
    // Sizes are always written as 8-byte vints: valid EBML, no second pass.
    function idBytes(id) {
        const out = [];
        let v = id;
        while (v > 0) { out.unshift(v & 0xff); v = Math.floor(v / 256); }
        return out;
    }
    function sizeBytes(n) {
        const out = [0x01];
        for (let i = 6; i >= 0; i--) out.push(Math.floor(n / Math.pow(2, i * 8)) & 0xff);
        return out;
    }
    function uintBytes(n) {
        const out = [];
        let v = n;
        do { out.unshift(v & 0xff); v = Math.floor(v / 256); } while (v > 0);
        return out;
    }
    function concat(parts) {
        let len = 0;
        for (const p of parts) len += p.length;
        const out = new Uint8Array(len);
        let o = 0;
        for (const p of parts) { out.set(p, o); o += p.length; }
        return out;
    }
    function el(id, payload) {
        const body = payload instanceof Uint8Array ? payload : new Uint8Array(payload);
        return concat([new Uint8Array(idBytes(id)), new Uint8Array(sizeBytes(body.length)), body]);
    }
    const uint = (id, n) => el(id, uintBytes(n));
    const str = (id, s) => el(id, Array.from(s).map((c) => c.charCodeAt(0) & 0x7f));
    function float(id, f) {
        const b = new Uint8Array(8);
        new DataView(b.buffer).setFloat64(0, f);
        return el(id, b);
    }
    const master = (id, children) => el(id, concat(children));

    function webm(width, height, chunks, durationMs) {
        const header = master(0x1A45DFA3, [
            uint(0x4286, 1), uint(0x42F7, 1), uint(0x42F2, 4), uint(0x42F3, 8),
            str(0x4282, 'webm'), uint(0x4287, 2), uint(0x4285, 2),
        ]);
        const info = master(0x1549A966, [
            uint(0x2AD7B1, 1000000),          // timecodes in milliseconds
            str(0x4D80, 'NexusAC'), str(0x5741, 'NexusAC'),
            float(0x4489, durationMs),
        ]);
        const tracks = master(0x1654AE6B, [
            master(0xAE, [
                uint(0xD7, 1), uint(0x73C5, 1), uint(0x83, 1), uint(0x9C, 0),
                str(0x86, 'V_VP8'),
                master(0xE0, [uint(0xB0, width), uint(0xBA, height)]),
            ]),
        ]);
        // One cluster per keyframe; block times are int16 ms relative to it.
        const clusters = [];
        let cur = null;
        for (const c of chunks) {
            if (!cur || c.key || c.ms - cur.base > 30000) {
                cur = { base: c.ms, blocks: [] };
                clusters.push(cur);
            }
            const rel = c.ms - cur.base;
            const head = new Uint8Array([0x81, (rel >> 8) & 0xff, rel & 0xff, c.key ? 0x80 : 0x00]);
            cur.blocks.push(el(0xA3, concat([head, c.data])));
        }
        const clusterEls = clusters.map((cl) => master(0x1F43B675, [uint(0xE7, cl.base)].concat(cl.blocks)));
        const segment = master(0x18538067, [info, tracks].concat(clusterEls));
        return concat([header, segment]);
    }

    // ------------------------------------------------------------- encoding
    function loadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => reject(new Error('frame did not decode'));
            img.src = src;
        });
    }
    function toDataURL(bytes) {
        return new Promise((resolve) => {
            const r = new FileReader();
            r.onload = () => resolve(r.result);
            r.readAsDataURL(new Blob([bytes], { type: 'video/webm' }));
        });
    }

    async function encode(frames, opts) {
        opts = opts || {};
        if (typeof VideoEncoder === 'undefined' || typeof VideoFrame === 'undefined') throw new Error('this game browser cannot encode video (no WebCodecs)');
        const list = frames.filter((f) => f && typeof f.data === 'string').slice().sort((a, b) => a.t - b.t);
        if (list.length < 2) throw new Error('not enough frames for a clip');

        const first = await loadImage(list[0].data);
        const maxW = Math.max(160, Number(opts.maxWidth) || 640);
        const scale = Math.min(1, maxW / first.naturalWidth);
        // VP8 wants even dimensions.
        const width = Math.max(2, Math.floor(first.naturalWidth * scale / 2) * 2);
        const height = Math.max(2, Math.floor(first.naturalHeight * scale / 2) * 2);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d', { alpha: false });

        const chunks = [];
        let failure = null;
        const encoder = new VideoEncoder({
            output: (chunk) => {
                const data = new Uint8Array(chunk.byteLength);
                chunk.copyTo(data);
                chunks.push({ ms: Math.round(chunk.timestamp / 1000), key: chunk.type === 'key', data });
            },
            error: (e) => { failure = e; },
        });
        const t0 = list[0].t;
        const span = Math.max(1, list[list.length - 1].t - t0);
        const config = {
            codec: 'vp8', width, height,
            bitrate: Math.max(200000, Number(opts.bitrate) || 900000),
            framerate: Math.max(1, Math.round(list.length * 1000 / span)),
            hardwareAcceleration: 'prefer-software',
        };
        const support = await VideoEncoder.isConfigSupported(config).catch(() => null);
        if (!support || !support.supported) throw new Error('VP8 encoding is not supported here');
        encoder.configure(config);

        let lastMs = -1;
        for (let i = 0; i < list.length; i++) {
            const img = i === 0 ? first : await loadImage(list[i].data).catch(() => null);
            if (!img) continue;
            ctx.drawImage(img, 0, 0, width, height);
            // Strictly increasing timestamps (two frames can share a ms).
            const ms = Math.max(lastMs + 1, Math.round(list[i].t - t0));
            lastMs = ms;
            const vf = new VideoFrame(canvas, { timestamp: ms * 1000 });
            encoder.encode(vf, { keyFrame: i % 20 === 0 });
            vf.close();
            if (failure) break;
        }
        await encoder.flush();
        encoder.close();
        if (failure) throw failure;
        if (!chunks.length) throw new Error('the encoder produced nothing');

        chunks.sort((a, b) => a.ms - b.ms);
        // The last frame stays on screen for one average frame gap.
        const durationMs = lastMs + Math.max(100, Math.round(span / list.length));
        return toDataURL(webm(width, height, chunks, durationMs));
    }

    window.NexusClip = { encode, _webm: webm };
})();

/*  NexusAC glue (2026-10-13): Nexus-Screens is gone, screenshot-basic takes the
    frames (client/cl_banclip.lua) and this page turns them into the ban clip
    plus smaller stills for Discord, then hands both back to the game.

    message { nexusClip: { id, frames: [{ t, data }], bitrate, maxWidth, stillWidth, stillQuality, stills: [index...] } }
    -> POST https://<resource>/nexusClipDone { id, clip, clipError, stills: [{ t, data }] }
*/
(function () {
    const RES = typeof GetParentResourceName === 'function' ? GetParentResourceName() : 'NexusAC';
    function load(src) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = () => resolve(null);
            img.src = src;
        });
    }
    async function still(data, width, quality) {
        const img = await load(data);
        if (!img) return null;
        const scale = Math.min(1, width / img.naturalWidth);
        const c = document.createElement('canvas');
        c.width = Math.max(2, Math.round(img.naturalWidth * scale));
        c.height = Math.max(2, Math.round(img.naturalHeight * scale));
        c.getContext('2d', { alpha: false }).drawImage(img, 0, 0, c.width, c.height);
        return c.toDataURL('image/jpeg', quality);
    }
    function reply(body) {
        fetch(`https://${RES}/nexusClipDone`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).catch(() => {});
    }
    window.addEventListener('message', async (event) => {
        const job = event.data && event.data.nexusClip;
        if (!job) return;
        const frames = Array.isArray(job.frames) ? job.frames : [];
        const out = { id: job.id, clip: null, clipError: null, stills: [] };
        try {
            for (const i of (job.stills || [])) {
                const f = frames[i];
                if (!f) continue;
                const d = await still(f.data, Number(job.stillWidth) || 1280, Number(job.stillQuality) || 0.7);
                if (d) out.stills.push({ t: f.t, data: d });
            }
        } catch (e) { /* stills are best effort */ }
        if (job.noClip) {
            out.clipError = 'no clip for this detector';
        } else if (frames.length >= 3) {
            try { out.clip = await window.NexusClip.encode(frames, { bitrate: job.bitrate, maxWidth: job.maxWidth }); }
            catch (e) { out.clipError = String(e && e.message || e).slice(0, 200); }
        } else {
            out.clipError = 'not enough frames for a clip';
        }
        reply(out);
    });
})();
