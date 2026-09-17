// keep-Alive audio controller.
//
// One AudioContext, two buses into the speaker:
//
//   metronome ── metroBus (ducked while a line plays) ──┐
//                                                       ├── destination
//   clips + agent voice ── voiceBus ────────────────────┘
//
// Metronome clicks are scheduled on the audio clock a few seconds ahead, so a
// stalled or throttled main thread doesn't break the beat. (Not a looping
// buffer: in Chromium 152 a loop over the whole buffer plays once and stops.)
//
// Everything spoken goes through one priority queue, one line at a time:
// pre-rendered protocol clips, and the AssemblyAI Voice Agent's replies, which
// arrive as streamed PCM16 chunks (openStream). While one of our clips is
// audible the controller reports the mic as gated, so the agent doesn't hear
// the app's own voice. Agent replies leave the mic open, so its barge-in still
// hears the caller.
//
// Priorities (set per clip in audio/manifest.json):
//   critical  cuts whatever is playing — an agent reply included — and plays next
//   response  answer to a question — waits for the line that's playing, but
//             jumps ahead of every queued protocol line
//   normal    protocol line, FIFO
//
// Events (addEventListener): clipstart, clipend, queue, gate, metronome, state.

const RANK = { critical: 0, response: 1, normal: 2 };

export const DEFAULTS = {
  bpm: 110,
  // Beat audibility, tested on a phone speaker (Sep 16): at 1.5 kHz the click sat in the
  // speech band and the voice masked it. At 3 kHz it cuts through, so it can stay quiet.
  metronomeGainDb: -3,
  clickHz: 3000,
  clickMs: 30,
  clickDecayMs: 5,
  metronomeAheadMs: 3000,   // clicks queued on the audio clock; covers 1 s background-tab timer throttling

  // Rana's spec, Sep 10. Duck depth -14 → -8 dB on Sep 14, then -8 → -4 dB on Sep 16,
  // both after listening on a phone speaker: at -14 the beat vanished under the voice,
  // at -8 it was still too faint to keep compressing to.
  duckDb: -4,
  duckAttackMs: 40,
  duckReleaseMs: 150,
  duck: { critical: true, normal: true, response: true },

  interruptFadeMs: 12,      // short enough to feel instant, long enough not to click
  clipGapMs: 250,           // pause between back-to-back lines; metronome stays ducked
  gateTailMs: 250,          // mic stays gated after the voice stops: output latency + room echo
  requeueInterrupted: true, // a normal line cut by a critical one plays again afterwards

  streamJitterMs: 60,       // head start before a streamed reply plays, and after a network gap
  streamGate: false,        // agent replies keep the mic open, so the Voice Agent's barge-in hears the caller
  // Live answers voiced as Sarah by ElevenLabs Flash (pcm_24000) arrive at about
  // -15.7 LUFS against -14 for the clips (measured Sep 17): lift them to match.
  streamGainDb: 1.7,

  // What the mic gate does while our own voice is audible. 'mute' is safe but deaf:
  // with silence going out, the Voice Agent can't report that the caller started
  // speaking, so nobody can barge in during a protocol line. 'attenuate' keeps a
  // shout audible; 'off' leaves it to echo cancellation. Pick after measuring the
  // leak on the demo laptop with the bench's "Mic → STT test".
  // Sep 17: 'off', agreed with Rana. Chrome's echo cancellation removes 32 dB of our
  // voice (leak-test.html) and the backend drops transcripts that match the line being
  // spoken, so the rescuer can interrupt at any moment.
  micGate: 'off',           // 'mute' | 'attenuate' | 'off'
  micGateAttenuateDb: -18,

  // The caller started talking: our line steps back instead of talking over them.
  yieldDuckDb: -12,
  yieldAttackMs: 60,
  yieldReleaseMs: 200,
  yieldPriorities: { critical: false, normal: true, response: true }, // a critical alert never steps back
};

const dbToGain = (db) => Math.pow(10, db / 20);

// Freeze a param at its current value so a new ramp starts from where it is now.
function hold(param, t) {
  if (param.cancelAndHoldAtTime) {
    param.cancelAndHoldAtTime(t);
  } else {
    const v = param.value;
    param.cancelScheduledValues(t);
    param.setValueAtTime(v, t);
  }
}

function base64ToInt16(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Int16Array(bytes.buffer, 0, bytes.length >> 1);
}

function bytesToBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

// Runs on the audio thread: resamples the mic to the target rate (linear
// interpolation, carried across 128-sample blocks) and posts PCM16 frames.
const PCM16_WORKLET = `
class Pcm16Sender extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { targetRate, frameSamples } = options.processorOptions;
    this.step = sampleRate / targetRate; // input samples per output sample
    this.pos = 0;                         // next output position in input samples, relative to this block
    this.prev = 0;                        // last sample of the previous block, i.e. index -1
    this.frameSamples = frameSamples;     // kept here: a transferred frame's own length reads 0
    this.frame = new Int16Array(frameSamples);
    this.n = 0;
  }
  process(inputs) {
    const x = inputs[0][0];
    if (!x) return true;
    const last = x.length - 1;
    while (this.pos < last) {
      const i = Math.floor(this.pos);
      const a = i < 0 ? this.prev : x[i];
      const s = a + (x[i + 1] - a) * (this.pos - i);
      this.frame[this.n++] = Math.max(-1, Math.min(1, s)) * 32767;
      if (this.n === this.frameSamples) {
        const full = this.frame;
        this.frame = new Int16Array(this.frameSamples); // allocate before transferring
        this.n = 0;
        this.port.postMessage(full.buffer, [full.buffer]);
      }
      this.pos += this.step;
    }
    this.pos -= x.length;
    this.prev = x[last];
    return true;
  }
}
registerProcessor('pcm16-sender', Pcm16Sender);
`;

export class AudioController extends EventTarget {
  constructor(options = {}) {
    super();
    this.opts = { ...DEFAULTS, ...options, duck: { ...DEFAULTS.duck, ...options.duck } };
    this.clips = new Map();
    this.spec = null;
    this.queue = [];
    this.current = null;
    this._earliestStart = 0;
    this._gated = false;
    this._gateTimer = null;
    this._metro = null;
    this._streamSeq = 0;
    this._worklet = null;
    this._userSpeaking = false;

    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx({ latencyHint: 'interactive' });
    // A -3 dBFS click on top of a -1 dBTP voice sums past full scale, so the buses meet
    // in a limiter rather than clipping at the speaker.
    this.master = this.ctx.createDynamicsCompressor();
    this.master.threshold.value = -3;
    this.master.knee.value = 0;
    this.master.ratio.value = 20;
    this.master.attack.value = 0.001;
    this.master.release.value = 0.08;
    this.master.connect(this.ctx.destination);

    this.metroBus = this.ctx.createGain();
    this.voiceBus = this.ctx.createGain();
    this.metroBus.connect(this.master);
    this.voiceBus.connect(this.master);

    // Level taps for meters and the test bench; analysers pass nothing downstream.
    this.taps = {
      metro: this.ctx.createAnalyser(),
      voice: this.ctx.createAnalyser(),
      master: this.ctx.createAnalyser(), // after the limiter: what the speaker gets
    };
    this.taps.metro.fftSize = this.taps.voice.fftSize = this.taps.master.fftSize = 2048;
    this.metroBus.connect(this.taps.metro);
    this.voiceBus.connect(this.taps.voice);
    this.master.connect(this.taps.master);

    this.ctx.addEventListener('statechange', () => this._emit('state', { state: this.ctx.state }));
  }

  // --- setup -----------------------------------------------------------------

  async load(manifestUrl = 'audio/manifest.json') {
    const base = new URL(manifestUrl, location.href);
    const res = await fetch(base);
    if (!res.ok) throw new Error(`manifest ${res.status}: ${base}`);
    const manifest = await res.json();
    this.spec = manifest.spec;

    await Promise.all(Object.entries(manifest.clips).map(async ([id, clip]) => {
      const r = await fetch(new URL(clip.file, base));
      if (!r.ok) throw new Error(`${clip.file} ${r.status}`);
      const buffer = await this.ctx.decodeAudioData(await r.arrayBuffer());
      this.clips.set(id, { id, buffer, priority: clip.priority, text: clip.text });
    }));
    return manifest;
  }

  // Call from a user gesture (the "Emergency" tap).
  async unlock() {
    // iOS: without this the ringer switch mutes Web Audio — a phone on silent would say nothing.
    if (navigator.audioSession) navigator.audioSession.type = 'playback';
    await this.ctx.resume();
  }

  // --- metronome -------------------------------------------------------------

  startMetronome(bpm = this.opts.bpm) {
    this.stopMetronome();
    const ctx = this.ctx;
    const m = {
      click: this._clickBuffer(),
      period: 60 / bpm,
      startAt: ctx.currentTime + 0.05,
      next: 0,            // index of the next beat to schedule
      live: new Set(),    // scheduled or playing click sources, so stop can cancel them
      timer: null,
    };

    // Beat n is always at startAt + n * period — computed, never accumulated, so no drift.
    const schedule = () => {
      const horizon = ctx.currentTime + this.opts.metronomeAheadMs / 1000;
      for (let t = m.startAt + m.next * m.period; t < horizon; t = m.startAt + ++m.next * m.period) {
        if (t < ctx.currentTime) continue; // main thread stalled past this beat; don't fire it late
        const src = ctx.createBufferSource();
        src.buffer = m.click;
        src.connect(this.metroBus);
        src.onended = () => m.live.delete(src);
        src.start(t);
        m.live.add(src);
      }
    };
    schedule();
    m.timer = setInterval(schedule, 250);
    this._metro = m;
    this._emit('metronome', { running: true, bpm });
  }

  stopMetronome() {
    const m = this._metro;
    if (!m) return;
    clearInterval(m.timer);
    for (const src of m.live) src.stop();
    this._metro = null;
    this._emit('metronome', { running: false });
  }

  _clickBuffer() {
    const sr = this.ctx.sampleRate;
    const n = Math.round(sr * this.opts.clickMs / 1000);
    const buf = this.ctx.createBuffer(1, n, sr);
    const data = buf.getChannelData(0);
    const attack = 0.001 * sr; // 1 ms, so the click itself doesn't click
    const decay = this.opts.clickDecayMs / 1000 * sr;
    const w = 2 * Math.PI * this.opts.clickHz / sr;
    let peak = 0;
    for (let i = 0; i < n; i++) {
      data[i] = Math.min(1, i / attack) * Math.exp(-i / decay) * Math.sin(w * i);
      peak = Math.max(peak, Math.abs(data[i]));
    }
    // Scale so the click peaks exactly at metronomeGainDb.
    const k = dbToGain(this.opts.metronomeGainDb) / peak;
    for (let i = 0; i < n; i++) data[i] *= k;
    return buf;
  }

  get metronomeRunning() {
    return this._metro !== null;
  }

  // Where the audible beat is right now, for syncing visuals. null when stopped.
  beatPhase() {
    const m = this._metro;
    if (!m) return null;
    const t = this.ctx.currentTime - (this.ctx.outputLatency || 0) - m.startAt;
    if (t < 0) return null;
    const beats = t / m.period;
    return { index: Math.floor(beats), phase: beats % 1 };
  }

  // --- lines -----------------------------------------------------------------

  play(id) {
    const clip = this.clips.get(id);
    if (!clip) throw new Error(`unknown clip: ${id}`);
    this._submit({ ...clip });
  }

  // A whole AudioBuffer from anywhere else.
  playBuffer(buffer, { id = 'live', priority = 'response', text = '' } = {}) {
    this._submit({ id, buffer, priority, text });
  }

  // An AssemblyAI Voice Agent reply. Open it at `reply.started`, push() every
  // `reply.audio` chunk (the base64 `data` string, or an Int16Array), then
  // end() at `reply.done` "completed" — or flush() if it was "interrupted".
  // turnEndedAt: performance.now() at `input.speech.stopped`, so clipstart can
  // report caller-stops-talking → agent-audible for the latency pill.
  openStream({
    id = `agent-${++this._streamSeq}`,
    priority = 'response',
    sampleRate = 24000,
    text = '',
    turnEndedAt = null,
    gate = this.opts.streamGate,
    gainDb = 0,
  } = {}) {
    const item = { id, priority, text, gate, turnEndedAt, gainDb, stream: { chunks: [], sampleRate, ended: false, dropped: false } };
    this._submit(item);
    return {
      id,
      push: (data) => this._pushChunk(item, data),
      end: () => {
        item.stream.ended = true;
        this._maybeFinishStream(item);
      },
      flush: () => this._flushStream(item),
      get dropped() {
        return item.stream.dropped;
      },
    };
  }

  // One voice everywhere: the agent's answer text is voiced as Sarah by ElevenLabs
  // on the backend, which streams raw PCM16 back (output_format=pcm_24000). Pass
  // the fetch() Response here. Chunk boundaries can split a sample, so an odd
  // byte is carried over. If a critical line cuts the answer, the download stops.
  async playPcmResponse(response, { sampleRate = 24000, ...opts } = {}) {
    if (!response.ok) throw new Error(`speech stream ${response.status}`);
    const reply = this.openStream({ sampleRate, gainDb: this.opts.streamGainDb, ...opts });
    const reader = response.body.getReader();
    let carry = null;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        if (reply.dropped) {
          await reader.cancel();
          return reply;
        }
        let bytes = value;
        if (carry) {
          bytes = new Uint8Array(carry.length + value.length);
          bytes.set(carry);
          bytes.set(value, carry.length);
        }
        const even = bytes.length - (bytes.length % 2);
        if (even) reply.push(new Int16Array(bytes.slice(0, even).buffer));
        carry = even < bytes.length ? bytes.slice(even) : null;
      }
      reply.end();
    } catch (err) {
      reply.flush();
      throw err;
    }
    return reply;
  }

  // Cut the current line and drop everything queued. The metronome keeps going.
  stop() {
    for (const q of this.queue) if (q.stream) q.stream.dropped = true;
    this.queue.length = 0;
    this._cut('stopped');
    this._emitQueue();
    this._release();
    this._setGate(false);
  }

  // --- mic -------------------------------------------------------------------

  // The mic as a MediaStream for any STT sender: silence while one of our clips
  // is audible (plus the gate tail), the mic otherwise. The stream never stops.
  // Request the mic with { echoCancellation: true } too — the gate covers our
  // voice, not the metronome clicks between lines.
  gateMic(micStream) {
    const src = this.ctx.createMediaStreamSource(micStream);
    const out = this.ctx.createMediaStreamDestination();
    src.connect(this._gateNode()).connect(out);
    return out.stream;
  }

  // The mic in the shape the Voice Agent API's `input.audio` wants: base64 PCM16
  // mono, 24 kHz, one frame every frameMs. Gated like gateMic — the frames keep
  // coming, as zeros while our clip is audible. Returns a stop function.
  async micToPcm16(micStream, { sampleRate = 24000, frameMs = 50, onFrame } = {}) {
    if (!this._worklet) {
      const url = URL.createObjectURL(new Blob([PCM16_WORKLET], { type: 'text/javascript' }));
      this._worklet = this.ctx.audioWorklet.addModule(url);
    }
    await this._worklet;

    const src = this.ctx.createMediaStreamSource(micStream);
    const node = new AudioWorkletNode(this.ctx, 'pcm16-sender', {
      channelCount: 1,
      channelCountMode: 'explicit', // stereo mics are mixed down to mono
      processorOptions: { targetRate: sampleRate, frameSamples: Math.round(sampleRate * frameMs / 1000) },
    });
    // The worklet has to be pulled by the graph to run; a muted path to the speaker does that.
    const sink = this.ctx.createGain();
    sink.gain.value = 0;
    src.connect(this._gateNode()).connect(node).connect(sink).connect(this.ctx.destination);
    node.port.onmessage = (e) => onFrame(bytesToBase64(new Uint8Array(e.data)));

    return () => {
      node.port.onmessage = null;
      src.disconnect();
      node.disconnect();
    };
  }

  _gateNode() {
    const closed = () => (this.opts.micGate === 'off' ? 1
      : this.opts.micGate === 'attenuate' ? dbToGain(this.opts.micGateAttenuateDb)
      : 0);
    const gate = this.ctx.createGain();
    gate.gain.value = this._gated ? closed() : 1;
    this.addEventListener('gate', (e) => {
      const t = this.ctx.currentTime;
      hold(gate.gain, t);
      gate.gain.linearRampToValueAtTime(e.detail.gated ? closed() : 1, t + 0.01);
    });
    return gate;
  }

  // The caller is talking: call this on the Voice Agent's `input.speech.started`
  // and `input.speech.stopped`. The line that's playing steps back instead of
  // talking over them, and nothing new starts until they stop — except a critical
  // alert, which is exactly the thing that must be heard over a panicking rescuer.
  userSpeaking(on) {
    if (this._userSpeaking === on) return;
    this._userSpeaking = on;
    this._emit('user', { speaking: on });

    const cur = this.current;
    if (cur && this._yields(cur.item)) {
      this._ramp(cur.gain.gain, on ? cur.baseGain * dbToGain(this.opts.yieldDuckDb) : cur.baseGain,
        on ? this.opts.yieldAttackMs : this.opts.yieldReleaseMs);
    }
    if (!on) this._next(); // release anything held back while they were talking
  }

  get userIsSpeaking() {
    return this._userSpeaking;
  }

  _yields(item) {
    return this.opts.yieldPriorities[item.priority] !== false;
  }

  get gated() {
    return this._gated;
  }

  get nowPlaying() {
    return this.current ? this.current.item.id : null;
  }

  get queued() {
    return this.queue.map((q) => q.id);
  }

  // --- queue -----------------------------------------------------------------

  _submit(item) {
    if (!(item.priority in RANK)) throw new Error(`bad priority: ${item.priority}`);

    // Same line already playing or waiting: don't stack it. STT can flag
    // "gasping" several times in a row.
    if (this.current?.item.id === item.id || this.queue.some((q) => q.id === item.id)) return;

    item.requestedAt = this.ctx.currentTime;
    if (item.priority === 'critical' && this.current) {
      const cut = this._cut('preempted');
      if (cut && cut.priority === 'normal' && this.opts.requeueInterrupted) {
        cut.requestedAt = null; // a replay, not a fresh trigger: no latency to report
        this._insert(cut, true);
      }
    }
    this._insert(item);
    this._emitQueue();
    if (!this.current) this._next();
  }

  // Keep the queue ordered by rank. New items go behind their equals; a requeued
  // line goes in front of them.
  _insert(item, front = false) {
    const r = RANK[item.priority];
    let i = this.queue.findIndex((q) => (front ? RANK[q.priority] >= r : RANK[q.priority] > r));
    if (i === -1) i = this.queue.length;
    this.queue.splice(i, 0, item);
  }

  _next() {
    if (this.current) return;
    const next = this.queue[0];
    // Nothing to say, or the caller is talking and this line can wait.
    if (!next || (this._userSpeaking && this._yields(next))) {
      this._release();
      this._setGate(false);
      return;
    }
    const item = this.queue.shift();
    this._emitQueue();

    const ctx = this.ctx;
    const startAt = Math.max(ctx.currentTime, this._earliestStart);
    if (this.opts.duck[item.priority]) this._duck();
    else this._release();
    this._setGate(item.gate !== false);

    const gain = ctx.createGain();
    gain.gain.value = dbToGain(item.gainDb || 0);
    gain.connect(this.voiceBus);
    const cur = { item, gain, baseGain: gain.gain.value, sources: new Set(), started: false, nextAt: startAt };
    this.current = cur;

    if (item.stream) {
      // Chunks that arrived while waiting go out back to back; later ones are
      // scheduled as they come in. With nothing buffered yet, give the network a head start.
      if (!item.stream.chunks.length) cur.nextAt += this.opts.streamJitterMs / 1000;
      for (const buf of item.stream.chunks) this._scheduleChunk(cur, buf);
      item.stream.chunks = [];
      this._maybeFinishStream(item);
      return;
    }

    const src = ctx.createBufferSource();
    src.buffer = item.buffer;
    src.connect(gain);
    src.start(startAt);
    cur.sources.add(src);
    src.onended = () => {
      if (this.current === cur) this._finish(cur);
    };
    cur.started = true;
    this._emitStart(item, startAt, item.buffer.duration);
  }

  _pushChunk(item, data) {
    const s = item.stream;
    if (s.dropped || s.ended) return;
    const pcm = typeof data === 'string' ? base64ToInt16(data) : data;
    if (!pcm.length) return;
    const buf = this.ctx.createBuffer(1, pcm.length, s.sampleRate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
    if (this.current?.item === item) this._scheduleChunk(this.current, buf);
    else s.chunks.push(buf);
  }

  _scheduleChunk(cur, buf) {
    const ctx = this.ctx;
    // A network gap drained the buffer: restart a jitter ahead rather than
    // firing late chunks into the past.
    if (cur.nextAt < ctx.currentTime) cur.nextAt = ctx.currentTime + this.opts.streamJitterMs / 1000;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(cur.gain);
    src.start(cur.nextAt);
    if (!cur.started) {
      cur.started = true;
      this._emitStart(cur.item, cur.nextAt, null);
    }
    cur.nextAt += buf.duration;
    cur.sources.add(src);
    src.onended = () => {
      cur.sources.delete(src);
      if (this.current === cur) this._maybeFinishStream(cur.item);
    };
  }

  _maybeFinishStream(item) {
    const cur = this.current;
    if (!cur || cur.item !== item || !item.stream.ended || cur.sources.size) return;
    this._finish(cur);
  }

  _flushStream(item) {
    item.stream.dropped = true;
    if (this.current?.item === item) {
      this._cut('interrupted');
      this._next();
      return;
    }
    const i = this.queue.indexOf(item);
    if (i !== -1) {
      this.queue.splice(i, 1);
      this._emitQueue();
    }
  }

  // The current line played out: short gap, then whatever is next.
  _finish(cur) {
    this.current = null;
    this._earliestStart = this.ctx.currentTime + this.opts.clipGapMs / 1000;
    if (cur.started) this._emit('clipend', { id: cur.item.id, priority: cur.item.priority, reason: 'ended' });
    this._next();
  }

  // Fade out and stop the current line. Returns the item that was cut, if any.
  _cut(reason) {
    const cur = this.current;
    if (!cur) return null;
    this.current = null;

    const t = this.ctx.currentTime;
    const f = this.opts.interruptFadeMs / 1000;
    hold(cur.gain.gain, t);
    cur.gain.gain.linearRampToValueAtTime(0, t + f);
    for (const src of cur.sources) {
      src.onended = null;
      src.stop(t + f);
    }
    this._earliestStart = t + f;
    if (cur.item.stream) cur.item.stream.dropped = true; // a cut reply is stale; ignore its late chunks

    if (cur.started) this._emit('clipend', { id: cur.item.id, priority: cur.item.priority, reason });
    return cur.item;
  }

  // clipstart carries two latencies for the dashboard's HUD pill:
  //   latencyMs      trigger → audible (queue wait, cut fade, output path). null for
  //                  a line replayed after a cut, since nothing new triggered it
  //   turnLatencyMs  caller stopped talking → agent audible, for Voice Agent replies
  _emitStart(item, startAt, duration) {
    const ctx = this.ctx;
    const outputLatency = (ctx.baseLatency || 0) + (ctx.outputLatency || 0);
    const toAudibleMs = (startAt - ctx.currentTime + outputLatency) * 1000;
    this._emit('clipstart', {
      id: item.id,
      priority: item.priority,
      text: item.text,
      stream: Boolean(item.stream),
      startAt,
      duration,
      latencyMs: item.requestedAt == null
        ? null
        : Math.round((startAt - item.requestedAt + outputLatency) * 1000),
      turnLatencyMs: item.turnEndedAt == null
        ? null
        : Math.round(performance.now() + toAudibleMs - item.turnEndedAt),
    });
  }

  // --- ducking and gating ----------------------------------------------------

  _duck() {
    this._ramp(this.metroBus.gain, dbToGain(this.opts.duckDb), this.opts.duckAttackMs);
  }

  _release() {
    this._ramp(this.metroBus.gain, 1, this.opts.duckReleaseMs);
  }

  // Exponential ramp: linear in dB, which is how a duck should sound.
  _ramp(param, target, ms) {
    const t = this.ctx.currentTime;
    hold(param, t);
    param.exponentialRampToValueAtTime(target, t + ms / 1000);
  }

  _setGate(on) {
    clearTimeout(this._gateTimer);
    if (on) {
      if (!this._gated) {
        this._gated = true;
        this._emit('gate', { gated: true });
      }
      return;
    }
    if (!this._gated) return;
    this._gateTimer = setTimeout(() => {
      this._gated = false;
      this._emit('gate', { gated: false });
    }, this.opts.gateTailMs);
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  _emitQueue() {
    this._emit('queue', { current: this.nowPlaying, queued: this.queued });
  }
}
