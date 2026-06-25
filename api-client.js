/**
 * API Client for Conversation Practice App
 * Handles authentication, token management, and API requests
 */

class APIClient {
    constructor() {
        // Detect environment and set baseURL accordingly
        const hostname = window.location.hostname;
        const port = window.location.port;
        const protocol = window.location.protocol;
        
        // If page is being served by Flask on port 4344, use relative paths
        // If page is opened directly (file://) or on different port, use full URL
        if (hostname === '' || protocol === 'file:') {
            // File opened directly - need full URL
            this.baseURL = 'http://localhost:4344';
        } else if (port === '4344' || (hostname === 'localhost' && port === '')) {
            // Already being served by Flask - use relative paths
            this.baseURL = '';
        } else if (hostname === 'localhost' || hostname === '127.0.0.1') {
            // Local but different port - use full URL
            this.baseURL = 'http://localhost:4344';
        } else {
            // Production/deployment - use relative paths
            this.baseURL = '';
        }
        
        this.token = localStorage.getItem('auth_token');
        try {
            const userStr = localStorage.getItem('conversation_user');
            this.user = userStr ? JSON.parse(userStr) : null;
        } catch (e) {
            console.warn('Error parsing user data:', e);
            this.user = null;
        }
    }

    /**
     * Set authorization token
     */
    setToken(token) {
        this.token = token;
        localStorage.setItem('auth_token', token);
    }

    /**
     * Get authorization headers
     */
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const portalTrial = window.portalDailyTrial;
        if (portalTrial && portalTrial.enabled) {
            headers['X-Portal-Trial'] = 'daily-10-min';
            headers['X-Portal-Email'] = portalTrial.email || '';
            headers['X-Portal-Name'] = portalTrial.name || '';
            headers['X-Portal-Trial-Date'] = portalTrial.dateKey || '';
            headers['X-Portal-Limit-Minutes'] = String(Math.round((portalTrial.limitSeconds || 600) / 60));
        }

        return headers;
    }

    /**
     * Fetch with timeout using AbortController
     */
    // Gemini / TTS can occasionally take longer (cold starts, congestion).
    // Default to a more forgiving timeout to avoid aborting valid requests.
    fetchWithTimeout(url, options, timeoutMs = 60000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        return fetch(url, {
            ...options,
            signal: controller.signal
        }).finally(() => clearTimeout(timeoutId));
    }

    /**
     * Handle API errors
     */
    async handleResponse(response) {
        if (response.status === 401) {
            // Token expired or invalid
            this.logout();
            window.location.href = '/';
            throw new Error('Session expired. Please login again.');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            // Preserve full error object for TTS errors with enable_url
            const errorMessage = error.error || error.message || `HTTP ${response.status}`;
            const errorObj = new Error(JSON.stringify(error)); // Pass full error as JSON string
            errorObj.status = response.status;
            errorObj.originalError = error;
            throw errorObj;
        }

        return response;
    }

    /**
     * Login/Register user
     */
    async login(email, password = '') {
        const response = await fetch(`${this.baseURL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        await this.handleResponse(response);
        const data = await response.json();

        this.setToken(data.token);
        this.user = data.user;
        localStorage.setItem('conversation_user', JSON.stringify(data.user));

        // Store usage data if provided
        if (data.usage) {
            localStorage.setItem('usage_data', JSON.stringify(data.usage));
        }

        return data;
    }

    /**
     * Logout user
     */
    logout() {
        this.token = null;
        this.user = null;
        localStorage.removeItem('auth_token');
        localStorage.removeItem('conversation_token');
        localStorage.removeItem('conversation_user');
        localStorage.removeItem('conversation_backup');
        localStorage.removeItem('usage_data');
        localStorage.removeItem('last_context');
        localStorage.removeItem('practice_mode');
    }

    /**
     * Send chat message
     */
    async chat(text, context, lessonLang = 'en', practiceMode = 'learning', meta = {}) {
        const response = await this.fetchWithTimeout(`${this.baseURL}/api/chat`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ text, context, lessonLang, practiceMode, ...meta })
        }, 60000);

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Send chat message using Server-Sent Events streaming.
     * Returns a promise that resolves with the final response once streaming
     * completes. `onPartial(accumulatedText, deltaText)` is called as text
     * arrives progressively so the UI can render the response appearing
     * character-by-character. Falls back to regular /api/chat on failure.
     *
     * On streaming success the final JSON has the same shape as /api/chat.
     */
    async chatStream(text, context, lessonLang = 'en', practiceMode = 'learning', meta = {}, onPartial = null) {
        const url = `${this.baseURL}/api/chat/stream`;
        const body = JSON.stringify({ text, context, lessonLang, practiceMode, ...meta });

        // Abort if the server goes silent for too long so a hung stream falls
        // back to /api/chat instead of leaving the student waiting forever.
        const controller = new AbortController();
        const STALL_TIMEOUT_MS = 45000;
        let stallTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT_MS);
        const resetStall = () => {
            clearTimeout(stallTimer);
            stallTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT_MS);
        };

        let response;
        try {
            response = await fetch(url, {
                method: 'POST',
                headers: {
                    ...this.getHeaders(),
                    'Accept': 'text/event-stream',
                },
                body,
                signal: controller.signal,
            });
        } catch (e) {
            clearTimeout(stallTimer);
            // Network error or stall abort  fall back to non-streaming chat
            console.warn('[chatStream] fetch failed, falling back to /api/chat:', e);
            return this.chat(text, context, lessonLang, practiceMode, meta);
        }

        // If server doesn't support stream, fall back. For real API errors
        // (429 limit, 500 provider error, auth problems), do not duplicate the
        // request against /api/chat; surface the original error instead.
        const ct = response.headers.get('content-type') || '';
        const canFallbackToChat = response.status === 404 || response.status === 405 || response.status === 501;
        if (!response.ok && !canFallbackToChat) {
            clearTimeout(stallTimer);
            await this.handleResponse(response);
        }
        if (canFallbackToChat || !ct.includes('text/event-stream')) {
            clearTimeout(stallTimer);
            console.warn(`[chatStream] server rejected stream (HTTP ${response.status}, ct=${ct}), falling back`);
            return this.chat(text, context, lessonLang, practiceMode, meta);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let finalPayload = null;
        let currentEvent = null;
        let lastAccumulated = '';

        const processLine = (line) => {
            if (line.startsWith('event:')) {
                currentEvent = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
                const raw = line.slice(5).trim();
                let data;
                try { data = JSON.parse(raw); } catch (_) { return; }
                if (currentEvent === 'partial' && data && typeof data.accumulated === 'string') {
                    const accumulated = data.accumulated;
                    const delta = data.delta || accumulated.slice(lastAccumulated.length);
                    lastAccumulated = accumulated;
                    if (typeof onPartial === 'function') {
                        try { onPartial(accumulated, delta); } catch (e) { console.warn('[chatStream] onPartial error:', e); }
                    }
                } else if (currentEvent === 'final') {
                    finalPayload = data;
                } else if (currentEvent === 'error') {
                    throw new Error(data?.error || 'stream error');
                }
            }
            // blank line separates SSE events  reset event name
            if (line === '') currentEvent = null;
        };

        try {
            while (true) {
                const { value, done } = await reader.read();
                resetStall();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                // Split by SSE line separators
                let idx;
                while ((idx = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.slice(0, idx).replace(/\r$/, '');
                    buffer = buffer.slice(idx + 1);
                    processLine(line);
                }
            }
            // Flush any remaining buffered line
            if (buffer.trim()) processLine(buffer.trim());
        } catch (e) {
            console.warn('[chatStream] stream read error, falling back:', e);
            return this.chat(text, context, lessonLang, practiceMode, meta);
        } finally {
            clearTimeout(stallTimer);
        }

        if (!finalPayload) {
            console.warn('[chatStream] stream ended without final event, falling back');
            return this.chat(text, context, lessonLang, practiceMode, meta);
        }

        return finalPayload;
    }

    /**
     * Free conversation actions (guided flow)
     */
    async freeConversationAction(action, payload = {}) {
        const response = await this.fetchWithTimeout(`${this.baseURL}/api/free-conversation`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ action, ...payload })
        }, 60000);

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Structured lesson actions (Learning mode with predefined layers)
     */
    async lesson(action, context, payload = {}) {
        const response = await this.fetchWithTimeout(`${this.baseURL}/api/lesson`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ action, context, ...payload })
        }, 60000);

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Generate report
     */
    async generateReport(conversation, context, practiceMode = 'learning', difficulty = 'intermediate') {
        const response = await fetch(`${this.baseURL}/api/report`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ conversation, context, practiceMode, difficulty })
        });

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Get TTS audio
     */
    async getTTS(text, speed = 1.0, lessonLang = 'en', voice = 'female2') {
        // Get voice from localStorage if not provided
        if (!voice || voice === 'undefined') {
            voice = localStorage.getItem('preferred_voice') || 'female2';
        }

        // Legacy aliases should not override backend-selected clone voice.
        const legacyVoiceHints = new Set(['lesson', 'achernar', 'female1', 'female2', 'male1', 'male2']);
        const normalizedVoice = String(voice || '').trim().toLowerCase();
        if (legacyVoiceHints.has(normalizedVoice)) {
            voice = '';
        }
        
        console.log(`[api-client] getTTS called with voice: ${voice}, lessonLang: ${lessonLang}`);
        
        const response = await this.fetchWithTimeout(`${this.baseURL}/api/tts`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ text, speed, lessonLang, voice })
        }, 25000);

        await this.handleResponse(response);
        return await response.blob();
    }

    /**
     * Export report as PDF
     */
    async exportPDF(report, userName) {
        const response = await fetch(`${this.baseURL}/api/export/pdf`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ report, user_name: userName })
        });

        await this.handleResponse(response);
        return await response.blob();
    }

    /**
     * Get conversation history
     */
    async getConversations() {
        const response = await fetch(`${this.baseURL}/api/conversations`, {
            method: 'GET',
            headers: this.getHeaders()
        });

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Clear conversation history
     */
    async clearConversations() {
        const response = await fetch(`${this.baseURL}/api/conversations`, {
            method: 'DELETE',
            headers: this.getHeaders()
        });

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Track usage time
     */
    async trackUsage(seconds) {
        try {
            const response = await fetch(`${this.baseURL}/api/usage/track`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({ seconds })
            });
            await this.handleResponse(response);
            return await response.json();
        } catch (err) {
            console.error('Failed to track usage:', err);
            return null;
        }
    }

    /**
     * Get current usage status
     */
    async getUsageStatus() {
        const response = await fetch(`${this.baseURL}/api/usage/status`, {
            method: 'GET',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: Get all authorized emails
     */
    async getAuthorizedEmails() {
        const response = await fetch(`${this.baseURL}/api/admin/emails`, {
            method: 'GET',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: Add email to authorized list
     */
    async addAuthorizedEmail(email) {
        const response = await fetch(`${this.baseURL}/api/admin/emails`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ email })
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: Remove email from authorized list
     */
    async removeAuthorizedEmail(email) {
        const response = await fetch(`${this.baseURL}/api/admin/emails/${encodeURIComponent(email)}`, {
            method: 'DELETE',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: Reload emails from file
     */
    async reloadEmails() {
        const response = await fetch(`${this.baseURL}/api/admin/emails/reload`, {
            method: 'POST',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: live dashboard metrics
     */
    async getAdminLiveMetrics(windowMinutes = 10) {
        const response = await fetch(`${this.baseURL}/api/admin/live-metrics?window_minutes=${encodeURIComponent(windowMinutes)}`, {
            method: 'GET',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Admin: weekly didactic report
     */
    async getAdminWeeklyReport(weeks = 8) {
        const response = await fetch(`${this.baseURL}/api/admin/weekly-report?weeks=${encodeURIComponent(weeks)}`, {
            method: 'GET',
            headers: this.getHeaders()
        });
        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return this.token !== null && this.user !== null;
    }

    /**
     * Get current user
     */
    getUser() {
        return this.user;
    }
}

// Export singleton instance
const apiClient = new APIClient();
