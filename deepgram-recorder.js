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

    static getMimeCandidates() {
        return [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/mp4;codecs=mp4a.40.2',
            'audio/mp4',
            'audio/aac',
            'audio/mpeg'
        ];
    }

    static getSupportStatus() {
        if (typeof window !== 'undefined' && window.isSecureContext === false) {
            return {
                supported: false,
                code: 'insecure_context',
                reason: 'O microfone so funciona em conexao segura. Abra pelo link HTTPS oficial ou use "Prefere digitar?".'
            };
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            return {
                supported: false,
                code: 'get_user_media_missing',
                reason: 'Este navegador nao liberou acesso ao microfone. Abra no Chrome ou Safari atualizado, ou use "Prefere digitar?".'
            };
        }
        if (typeof MediaRecorder === 'undefined') {
            return {
                supported: false,
                code: 'media_recorder_missing',
                reason: 'Este navegador nao consegue gravar audio aqui. Abra no Chrome ou Safari atualizado, ou use "Prefere digitar?".'
            };
        }
        return { supported: true, code: 'ok', reason: '' };
    }

    static getFriendlyMediaError(error) {
        const name = error && error.name ? error.name : '';
        if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
            return 'Permissao do microfone negada. Toque no cadeado do navegador e libere o microfone.';
        }
        if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
            return 'Nao encontrei microfone neste aparelho. Verifique o microfone ou use "Prefere digitar?".';
        }
        if (name === 'NotReadableError' || name === 'TrackStartError') {
            return 'O microfone esta ocupado por outro app. Feche chamadas/gravadores e tente de novo.';
        }
        if (name === 'SecurityError') {
            return 'O navegador bloqueou o microfone por seguranca. Abra pelo link HTTPS oficial.';
        }
        if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
            return 'Nao consegui iniciar o microfone com este aparelho. Tente outro navegador ou use "Prefere digitar?".';
        }
        return 'Nao consegui acessar o microfone. Verifique permissoes e tente novamente.';
    }

    async start() {
        try {
            const support = DeepgramRecorder.getSupportStatus();
            if (!support.supported) {
                return {
                    success: false,
                    error: support.reason,
                    code: support.code
                };
            }

            // Request microphone access
            const audioConstraints = [
                {
                    channelCount: { ideal: 1 },
                    sampleRate: { ideal: 48000 },
                    echoCancellation: { ideal: true },
                    noiseSuppression: { ideal: true },
                    autoGainControl: { ideal: true },
                    voiceIsolation: { ideal: true }
                },
                {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                },
                true
            ];

            let lastMediaError = null;
            for (const audio of audioConstraints) {
                try {
                    this.stream = await navigator.mediaDevices.getUserMedia({ audio });
                    break;
                } catch (err) {
                    lastMediaError = err;
                }
            }
            if (!this.stream) {
                throw lastMediaError || new Error('Microphone access failed');
            }

            const mimeCandidates = DeepgramRecorder.getMimeCandidates();
            const mimeType = mimeCandidates.find(t => MediaRecorder.isTypeSupported(t)) || '';
            console.log(`[Recorder] Using format: ${mimeType || 'browser default'}`);

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
            this.mediaRecorder.start(250);
            this.isRecording = true;

            console.log(`[Recorder] Recording started (format: ${this.actualMimeType})`);
            return { success: true };

        } catch (error) {
            console.error('[Recorder] Microphone access error:', error);
            return {
                success: false,
                error: DeepgramRecorder.getFriendlyMediaError(error),
                code: error && error.name ? error.name : 'microphone_error'
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

            try {
                this.mediaRecorder.requestData();
            } catch (_) {}

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
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const portalTrial = window.portalDailyTrial;
        if (portalTrial && portalTrial.enabled) {
            headers['X-Portal-Trial'] = 'daily-10-min';
            headers['X-Portal-Email'] = portalTrial.email || '';
            headers['X-Portal-Name'] = portalTrial.name || '';
            headers['X-Portal-Trial-Date'] = portalTrial.dateKey || '';
            headers['X-Portal-Limit-Minutes'] = String(Math.round((portalTrial.limitSeconds || 600) / 60));
        }

        const response = await fetch(`${baseURL}/api/transcribe`, {
            method: 'POST',
            headers,
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
            if (/no speech detected|audio file is empty|empty audio/i.test(String(rawError))) {
                return {
                    success: false,
                    error: rawError,
                    message: 'Nao consegui ouvir sua fala. Tente de novo, falando um pouco mais perto do microfone.',
                    retry: true,
                    status: response.status
                };
            }

            const isUsageBlocked = response.status === 429 && (
                data.portal_trial === true || /weekend practice limit reached|limite gratuito/i.test(String(rawError))
            );

            return {
                success: false,
                error: rawError,
                message: data.message || '',
                status: response.status,
                usageBlocked: isUsageBlocked,
                portal_trial: data.portal_trial === true,
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
