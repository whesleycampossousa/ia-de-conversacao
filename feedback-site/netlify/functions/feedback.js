const BLOB_URL = 'https://jsonblob.com/api/jsonBlob/019cc888-34e8-7c99-a2a3-9e26132d3da3';

const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json'
};

exports.handler = async (event) => {
    // Handle CORS preflight
    if (event.httpMethod === 'OPTIONS') {
        return { statusCode: 200, headers, body: '' };
    }

    try {
        // GET - Read all feedbacks
        if (event.httpMethod === 'GET') {
            const res = await fetch(BLOB_URL, {
                headers: { 'Accept': 'application/json' }
            });
            if (!res.ok) throw new Error('Failed to read from storage');
            const data = await res.text();
            return { statusCode: 200, headers, body: data };
        }

        // POST - Add new feedback
        if (event.httpMethod === 'POST') {
            const newFeedback = JSON.parse(event.body);

            // Validate
            if (!newFeedback.name || !newFeedback.rating || !newFeedback.comment) {
                return {
                    statusCode: 400,
                    headers,
                    body: JSON.stringify({ error: 'Missing required fields' })
                };
            }

            // Read current feedbacks
            const getRes = await fetch(BLOB_URL, {
                headers: { 'Accept': 'application/json' }
            });
            if (!getRes.ok) throw new Error('Failed to read from storage');
            const data = await getRes.json();

            // Append new feedback
            const feedbacks = Array.isArray(data.feedbacks) ? data.feedbacks : [];
            feedbacks.push({
                name: String(newFeedback.name).trim(),
                rating: parseInt(newFeedback.rating),
                comment: String(newFeedback.comment).trim(),
                date: new Date().toISOString()
            });

            // Save back
            const putRes = await fetch(BLOB_URL, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ feedbacks })
            });
            if (!putRes.ok) throw new Error('Failed to save to storage');

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ success: true, total: feedbacks.length })
            };
        }

        return {
            statusCode: 405,
            headers,
            body: JSON.stringify({ error: 'Method not allowed' })
        };

    } catch (err) {
        return {
            statusCode: 500,
            headers,
            body: JSON.stringify({ error: err.message || 'Internal error' })
        };
    }
};
