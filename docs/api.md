# AI CPO Agent API

This document outlines the HTTP endpoints for interacting with the AI Chief Product Officer (CPO) agent. Replace the base URL with wherever your service is deployed.

## Submit Prompt

`POST /api/agent`

Send a prompt or instruction to the AI CPO agent. The agent processes the input and returns a structured response.

**Request JSON**

```json
{
  "prompt": "Describe the roadmap for the next quarter."
}
```

**Response JSON**

```json
{
  "response": "Here is the roadmap..."
}
```

## Authentication

All API requests should include an API key in the `Authorization` header:

```
Authorization: Bearer YOUR_API_KEY
```

Replace `YOUR_API_KEY` with the secret key associated with your account.

## Rate Limits

The service may enforce rate limits per API key. Exceeding these limits will result in an HTTP `429 Too Many Requests` response. If you require higher limits, contact support.

## Error Responses

The API uses conventional HTTP status codes to indicate success or failure.

- **400 Bad Request** – The request was malformed or missing required fields.
- **401 Unauthorized** – API key missing or invalid.
- **429 Too Many Requests** – Rate limit exceeded.
- **500 Internal Server Error** – An unexpected error occurred on the server.

Error responses are returned in JSON format. Example:

```json
{
  "error": "Invalid API key."
}
```
