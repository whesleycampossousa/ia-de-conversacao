/**
 * Groq Whisper Audio Recording Module
 * Replaces Web Speech API with MediaRecorder + Groq Whisper cloud transcription
 */

class DeepgramRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.stream = null;
    }

    async start() {
        try {
            // Request microphone access
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                }
            });

            // Create MediaRecorder
            const options = { mimeType: 'audio/webm' };

            // Fallback for browsers that don't support webm
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options.mimeType = 'audio/mp4';
            }

            this.mediaRecorder = new MediaRecorder(this.stream, options);
            this.audioChunks = [];

            // Collect audio data
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            // Start recording
            this.mediaRecorder.start();
            this.isRecording = true;

            console.log('[Deepgram] Recording started');
            return { success: true };

        } catch (error) {
            console.error('[Deepgram] Microphone access error:', error);
            return {
                success: false,
                error: 'Could not access microphone. Please check permissions.'
            };
        }
    }

    async stop() {
        return new Promise((resolve, reject) => {
            if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
                reject(new Error('No active recording'));
                return;
            }

            this.mediaRecorder.onstop = async () => {
                this.isRecording = false;

                // Create audio blob
                const audioBlob = new Blob(this.audioChunks, {
                    type: this.mediaRecorder.mimeType
                });

                // Stop all tracks
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }

                console.log(`[Deepgram] Recording stopped. Size: ${audioBlob.size} bytes`);

                // Resolve with audio blob
                resolve(audioBlob);
            };

            // Stop recording
            this.mediaRecorder.stop();
        });
    }

    cancel() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        this.isRecording = false;
        this.audioChunks = [];
        console.log('[Deepgram] Recording cancelled');
    }
}

/**
 * Transcribe audio blob using Whisper API through our backend
 */
async function transcribeWithDeepgram(audioBlob, token, language = null) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');

    // Add language hint if provided
    if (language) {
        formData.append('language', language);
    }

    try {
        console.log(`[Deepgram] Sending audio for transcription${language ? ' with language hint: ' + language : ''}...`);

        const response = await fetch('/api/transcribe', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            // Check if backend suggests a retry (e.g. for hallucinations)
            if (data.retry) {
                return {
                    success: false,
                    error: data.message || 'Please try again',
                    retry: true
                };
            }
            throw new Error(data.error || data.message || 'Transcription failed');
        }

        console.log(`[Deepgram] Transcription success. Confidence: ${data.confidence}`);
        return {
            success: true,
            transcript: data.transcript,
            confidence: data.confidence
        };

    } catch (error) {
        console.error('[Deepgram] Transcription error:', error);
        return {
            success: false,
            error: error.message || 'Transcription failed'
        };
    }
}

// Export for use in app.js
window.DeepgramRecorder = DeepgramRecorder;
window.transcribeWithDeepgram = transcribeWithDeepgram;
