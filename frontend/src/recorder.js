import {useEffect, useRef, useState} from 'react';

// Records up to 28s of speech and hands the audio to onAudio(FormData).
export function useRecorder(onAudio, onError) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef(null), timer = useRef(null), stream = useRef(null);
  useEffect(() => () => {clearInterval(timer.current); stream.current?.getTracks().forEach(t => t.stop());}, []);
  async function toggle() {
    if (recording) {recorder.current?.stop(); return;}
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Microphone recording is unavailable. Use Chrome on localhost or type your notes.');
      const media = await navigator.mediaDevices.getUserMedia({audio:true}); stream.current = media;
      const mime = ['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
      if (!mime) {media.getTracks().forEach(t => t.stop()); throw new Error('No supported recording format. Please type your notes.');}
      const capture = new MediaRecorder(media, {mimeType:mime}); recorder.current = capture;
      const chunks = []; capture.ondataavailable = e => {if (e.data.size) chunks.push(e.data);};
      capture.onstop = () => {
        clearInterval(timer.current); media.getTracks().forEach(t => t.stop()); setRecording(false);
        const form = new FormData();
        form.append('audio', new Blob(chunks, {type:mime.split(';')[0]}), 'recording');
        onAudio(form);
      };
      capture.start(); setRecording(true); setSeconds(0);
      let elapsed = 0;
      timer.current = setInterval(() => {setSeconds(++elapsed); if (elapsed >= 28 && capture.state === 'recording') capture.stop();}, 1000);
    } catch (e) {onError(e.message); stream.current?.getTracks().forEach(t => t.stop());}
  }
  return {recording, seconds, toggle};
}
