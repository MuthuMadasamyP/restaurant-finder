(function () {
  "use strict";

  const API_BASE = window.location.protocol === "file:"
    ? "http://127.0.0.1:800/api"
    : `${window.location.origin}/api`;

  window.initSpeechInput = function initSpeechInput(options) {
    const input = document.getElementById(options.inputId);
    const button = document.getElementById(options.buttonId);
    const status = document.getElementById(options.statusId);

    if (!input || !button || !status) return;

    if (!navigator.mediaDevices?.getUserMedia || !(window.AudioContext || window.webkitAudioContext)) {
      button.disabled = true;
      button.title = "Microphone recording is not supported in this browser";
      status.textContent = "Speech input is not available in this browser.";
      return;
    }

    const recorder = createWavRecorder({
      onLevel: (level) => button.style.setProperty("--speech-level", String(level)),
    });

    let isListening = false;
    let committedText = "";

    button.addEventListener("click", async () => {
      if (isListening) {
        await stopListening();
        return;
      }

      await startListening();
    });

    async function startListening() {
      committedText = input.value.trim();
      setListeningState(true);
      status.textContent = "Listening for a location...";

      try {
        await recorder.start();
      } catch (err) {
        setListeningState(false);
        status.textContent = err.name === "NotAllowedError"
          ? "Allow microphone access to use speech input."
          : "Could not start microphone recording.";
      }
    }

    async function stopListening() {
      status.textContent = "Transcribing with Python speech recognition...";
      button.disabled = true;

      try {
        const wavBlob = await recorder.stop();
        const transcript = await transcribeAudio(wavBlob, options.lang || "en-IN");

        if (transcript) {
          input.value = mergeSpeechText(committedText, transcript);
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.focus();
          status.textContent = "Location captured.";
        } else {
          status.textContent = "No speech detected. Try again.";
        }
      } catch (err) {
        status.textContent = err.message || "Speech input stopped unexpectedly.";
      } finally {
        button.disabled = false;
        setListeningState(false);
      }
    }

    function setListeningState(active) {
      isListening = active;
      button.classList.toggle("is-listening", active);
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("aria-label", active ? "Stop speech input" : "Speak location");
      button.title = active ? "Stop speech input" : "Speak location";
      const label = button.querySelector(".speech-btn-label");
      if (label) label.textContent = active ? "Stop" : "Speak location";
      if (!active) button.style.removeProperty("--speech-level");
    }
  };

  async function transcribeAudio(blob, language) {
    const formData = new FormData();
    formData.append("audio", blob, "location.wav");
    formData.append("language", language);

    const response = await fetch(`${API_BASE}/speech/transcribe`, {
      method: "POST",
      body: formData,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Speech transcription failed.");
    }

    return (data.transcript || "").trim();
  }

  function createWavRecorder({ onLevel }) {
    let audioContext;
    let source;
    let processor;
    let stream;
    let chunks = [];
    let sampleRate = 44100;

    async function start() {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContext = new AudioContextCtor();
      sampleRate = audioContext.sampleRate;
      chunks = [];

      source = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
        onLevel?.(getAudioLevel(input));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
    }

    async function stop() {
      if (processor) {
        processor.disconnect();
        processor.onaudioprocess = null;
      }
      if (source) source.disconnect();
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (audioContext) await audioContext.close();

      const samples = flattenSamples(chunks);
      reset();
      return encodeWav(samples, sampleRate);
    }

    function reset() {
      audioContext = null;
      source = null;
      processor = null;
      stream = null;
      chunks = [];
    }

    return { start, stop };
  }

  function flattenSamples(chunks) {
    const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const samples = new Float32Array(length);
    let offset = 0;

    chunks.forEach((chunk) => {
      samples.set(chunk, offset);
      offset += chunk.length;
    });

    return samples;
  }

  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, "data");
    view.setUint32(40, samples.length * 2, true);

    let offset = 44;
    for (let i = 0; i < samples.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }

    return new Blob([view], { type: "audio/wav" });
  }

  function writeString(view, offset, value) {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  }

  function getAudioLevel(samples) {
    let total = 0;
    for (let i = 0; i < samples.length; i += 1) {
      total += samples[i] * samples[i];
    }
    return Math.min(Math.sqrt(total / samples.length) * 9, 1).toFixed(2);
  }

  function mergeSpeechText(existingText, transcript) {
    if (!existingText) return transcript;
    return `${existingText} ${transcript}`.replace(/\s+/g, " ").trim();
  }
})();
