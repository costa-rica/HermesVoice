# API Error Response Standards

## Standard Error Format

All API errors must return a consistent JSON structure:

```json
{
  "error": {
    "code": "ERROR_CODE_HERE",
    "message": "User-facing error message",
    "details": "Additional context (optional)",
    "status": 500
  }
}
```

## Field Definitions

- **`code`**: Machine-readable identifier (uppercase with underscores)
  - Examples: `MACHINE_RETRIEVAL_FAILED`, `INVALID_INPUT`, `AUTH_FAILED`
  - Used by clients for programmatic error handling

- **`message`**: Human-readable summary for display to users
  - Keep concise and clear
  - Avoid technical jargon when possible

- **`details`**: Optional additional context
  - Include for debugging in development
  - Sanitize or omit in production (never expose stack traces, DB errors, credentials)

- **`status`**: HTTP status code matching the response header

## Implementation

### Express.js

```javascript
// Single error
res.status(500).json({
  error: {
    code: "MACHINE_RETRIEVAL_FAILED",
    message: "Failed to retrieve machine information",
    details: process.env.NODE_ENV === 'development' ? err.message : undefined,
    status: 500
  }
});

// Validation errors
res.status(400).json({
  error: {
    code: "VALIDATION_ERROR",
    message: "Request validation failed",
    status: 400,
    details: [
      { field: "email", message: "Invalid email format" },
      { field: "age", message: "Must be 18 or older" }
    ]
  }
});
```

### Python (FastAPI/Flask)

```python
from fastapi.responses import JSONResponse

# Single error
return JSONResponse(
    status_code=500,
    content={
        "error": {
            "code": "MACHINE_RETRIEVAL_FAILED",
            "message": "Failed to retrieve machine information",
            "details": str(e) if settings.DEBUG else None,
            "status": 500
        }
    }
)

# Validation errors
return JSONResponse(
    status_code=400,
    content={
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "status": 400,
            "details": [
                {"field": "email", "message": "Invalid email format"},
                {"field": "age", "message": "Must be 18 or older"}
            ]
        }
    }
)
```

## Common Error Codes

Use consistent error codes across your APIs:

- `VALIDATION_ERROR` - Invalid request data (400)
- `AUTH_FAILED` - Authentication failure (401)
- `FORBIDDEN` - Insufficient permissions (403)
- `NOT_FOUND` - Resource doesn't exist (404)
- `CONFLICT` - Resource conflict (409)
- `RATE_LIMIT_EXCEEDED` - Too many requests (429)
- `INTERNAL_ERROR` - Server error (500)
- `SERVICE_UNAVAILABLE` - Temporary outage (503)

## Security Guidelines

1. **Never expose** in production:
   - Stack traces
   - Database error messages
   - File paths
   - Internal system details
   - Credentials or tokens

2. **Always include** the HTTP status code in both the response header AND the error body

3. **Log detailed errors** server-side for debugging, return sanitized versions to clients

4. **Be consistent** across all endpoints in all applications
