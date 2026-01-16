/**
 * API Client for Conversation Practice App
 * Handles authentication, token management, and API requests
 */

class APIClient {
    constructor() {
        this.baseURL = '';  // Relative paths for deployment
        this.token = localStorage.getItem('auth_token');
        this.user = JSON.parse(localStorage.getItem('conversation_user'));
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

        return headers;
    }

    /**
     * Handle API errors
     */
    async handleResponse(response) {
        if (response.status === 401) {
            // Token expired or invalid
            this.logout();
            window.location.href = 'login.html';
            throw new Error('Session expired. Please login again.');
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(error.error || `HTTP ${response.status}`);
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
        localStorage.removeItem('conversation_user');
        localStorage.removeItem('conversation_backup');
    }

    /**
     * Send chat message
     */
    async chat(text, context) {
        const response = await fetch(`${this.baseURL}/api/chat`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ text, context })
        });

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Generate report
     */
    async generateReport(conversation, context) {
        const response = await fetch(`${this.baseURL}/api/report`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ conversation, context })
        });

        await this.handleResponse(response);
        return await response.json();
    }

    /**
     * Get TTS audio
     */
    async getTTS(text, speed = 1.0) {
        const response = await fetch(`${this.baseURL}/api/tts`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify({ text, speed })
        });

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
