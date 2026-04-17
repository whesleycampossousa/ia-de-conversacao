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
        this.actualMimeType = 'audio/webm'; // track real format for backend
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

            // Try WebM first (Chrome, Firefox, Edge), then mp4 (Safari/iOS)
            let mimeType = 'audio/webm';
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                // Safari/iOS: try mp4 variants
                const mp4Types = ['audio/mp4', 'audio/aac', 'audio/mpeg'];
                mimeType = mp4Types.find(t => MediaRecorder.isTypeSupported(t)) || '';
                console.log(`[Recorder] WebM not supported, using: ${mimeType || 'browser default'}`);
            }

            const options = mimeType ? { mimeType } : {};
            this.mediaRecorder = new MediaRecorder(this.stream, options);
            this.actualMimeType = this.mediaRecorder.mimeType; // capture what browser actually chose
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

            console.log(`[Recorder] Recording started (format: ${this.actualMimeType})`);
            return { success: true };

        } catch (error) {
            console.error('[Recorder] Microphone access error:', error);
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

                // Create audio blob with the actual mimeType
                const audioBlob = new Blob(this.audioChunks, {
                    type: this.actualMimeType
                });

                // Stop all tracks
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }

                console.log(`[Recorder] Recording stopped. Size: ${audioBlob.size} bytes, format: ${this.actualMimeType}`);

                // Resolve with audio blob
                resolve(audioBlob);
            };

            // Stop recording
            this.mediaRecorder.stop();
        });
    }

    /** Return the actual MIME type the browser is recording with */
    getMimeType() {
        return this.actualMimeType;
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
        console.log('[Recorder] Recording cancelled');
    }
}

/**
 * Transcribe audio blob using Whisper API through our backend
 * @param {Blob} audioBlob - Recorded audio blob
 * @param {string} token - Auth token
 * @param {string|null} language - Language hint ('en' or 'pt')
 * @param {string} mimeType - Actual MIME type from the recorder
 */
async function transcribeWithDeepgram(audioBlob, token, language = null, mimeType = 'audio/webm') {
    const formData = new FormData();

    // Use correct file extension based on actual format
    const isWebm = mimeType.includes('webm');
    const filename = isWebm ? 'recording.webm' : 'recording.mp4';
    formData.append('audio', audioBlob, filename);

    // Send the actual MIME type so backend can configure providers correctly
    formData.append('mime_type', mimeType);

    // Add language hint if provided
    if (language) {
        formData.append('language', language);
    }

    try {
        console.log(`[STT] Sending ${audioBlob.size} bytes (${mimeType}) for transcription${language ? ', lang: ' + language : ''}...`);

        // Use apiClient baseURL if available, otherwise use relative path
        const baseURL = (typeof apiClient !== 'undefined' && apiClient.baseURL) ? apiClient.baseURL : '';
        const response = await fetch(`${baseURL}/api/transcribe`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        let data = {};
        try {
            data = await response.json();
        } catch (parseError) {
            console.warn('[STT] Failed to parse transcription response JSON:', parseError);
        }

        if (!response.ok) {
            // Check if backend suggests a retry (e.g. for hallucinations)
            if (data.retry) {
                return {
                    success: false,
                    error: data.message || 'Please try again',
                    retry: true
                };
            }

            const rawError = data.error || data.message || 'Transcription failed';
            const isUsageBlocked = response.status === 429 && /weekend practice limit reached/i.test(String(rawError));

            return {
                success: false,
                error: rawError,
                message: data.message || '',
                status: response.status,
                usageBlocked: isUsageBlocked,
                remaining_seconds: typeof data.remaining_seconds === 'number' ? data.remaining_seconds : null,
                is_weekend: typeof data.is_weekend === 'boolean' ? data.is_weekend : null
            };
        }

        console.log(`[STT] Success via ${data.provider || '?'}, confidence: ${data.confidence}`);
        return {
            success: true,
            transcript: data.text || data.transcript,
            confidence: data.confidence
        };

    } catch (error) {
        console.error('[STT] Transcription error:', error);
        return {
            success: false,
            error: error.message || 'Transcription failed'
        };
    }
}

// Export for use in app.js
window.DeepgramRecorder = DeepgramRecorder;
window.transcribeWithDeepgram = transcribeWithDeepgram;
