# LOGGING_PYTHON_V06

## Overview

This document defines **concise, production-aligned logging requirements** for Python services using **Loguru**.  
It mirrors Node.js behavior while remaining implementation-focused and explicit.

Python services use **`RUN_ENVIRONMENT`**, not `NODE_ENV`.

Valid values:

- `development`
- `testing`
- `production`

---

## Required Environment Variables (Fatal if Missing)

Missing required variables **MUST trigger immediate fatal errors** at startup.  
The error **MUST clearly name the missing variable** and exit with a non‑zero code.

| Variable          | Required In         | Fatal Behavior                    |
| ----------------- | ------------------- | --------------------------------- |
| `NAME_APP`        | All environments    | Fatal error if missing or empty   |
| `RUN_ENVIRONMENT` | All environments    | Fatal error if missing or invalid |
| `PATH_TO_LOGS`    | testing, production | Fatal error if missing            |

**Fatal error requirements:**

- Log at `ERROR` or `CRITICAL`
- Write to stderr
- Message MUST explicitly name the missing variable
- Application MUST NOT continue

---

## Logging Modes

### Development

- Output: Terminal only
- Level: `DEBUG` and above
- Files: Disabled

### Testing

- Output: Terminal **and** file
- Level: `INFO` and above
- Files: Enabled with rotation

### Production

- Output: File only
- Level: `INFO` and above
- Files: Enabled with rotation

---

## Environment Comparison Table

| Feature                  | Development | Testing | Production |
| ------------------------ | ----------- | ------- | ---------- |
| Terminal Output          | Yes         | Yes     | No         |
| File Output              | No          | Yes     | Yes        |
| Log Level                | DEBUG       | INFO    | INFO       |
| Rotation                 | No          | Yes     | Yes        |
| Process Safe (`enqueue`) | No          | Yes     | Yes        |

---

## Log File Behavior

- Filename: `{NAME_APP}.log`
- Directory: `PATH_TO_LOGS`
- Rotation:
  - Size: `LOG_MAX_SIZE_IN_MB` (default `3 MB`)
  - Retention: `LOG_MAX_FILES` (default `3`)
- Old files are deleted automatically

---

## Log Formatting Specs

**Development (Console):**

```
HH:MM:SS.mmm | LEVEL | module:function:line | message
```

**Testing / Production (File):**

```
YYYY-MM-DD HH:MM:SS.mmm | LEVEL | module:function:line | message
```

Formatting MUST include:

- Timestamp
- Level
- Code location
- Message

---

## Process Safety Requirements

- Testing and Production MUST enable:
  - `enqueue=True` (thread/process safety)
- No shared file handles between parent and child processes
- Each process initializes its own logger instance

---

## Early Exit Logging (Mandatory)

If the service exits early (startup guardrails, config failures, cron exits):

Required behavior:

1. Log the exit reason
2. Ensure it writes to the active sink (terminal or file)
3. Flush logs before exiting
4. Exit with a non‑zero code if failure-related

Early exits **MUST leave a log record** explaining why the service ran and stopped.

---

## Uncaught Exception Handling (Mandatory)

**Problem:** Systemd services may crash without writing errors to log files, causing silent failures.

**Solution:** Install `sys.excepthook` to catch and log all uncaught exceptions before exit.

Requirements:

- Log at `CRITICAL` with full traceback via `logger.opt(exception=...)`
- Preserve `KeyboardInterrupt` (allow Ctrl+C)
- Enable `backtrace=True` and `diagnose=True` on all sinks

---

## Child Process Rules

- Each child process MUST receive its own `NAME_APP`
- Parent injects child name via `NAME_CHILD_PROCESS_*`
- Parent and child log to separate files
- No process may write to another process’s log file

---

## Implementation Checklist

- [ ] Install Loguru
- [ ] Centralize logger configuration
- [ ] Validate required env vars at startup
- [ ] Fail fast with explicit fatal errors
- [ ] Configure sinks per `RUN_ENVIRONMENT`
- [ ] Enable rotation + retention
- [ ] Enable process safety where required
- [ ] Install `sys.excepthook` for uncaught exceptions
- [ ] Enable `backtrace=True` and `diagnose=True` on all sinks
- [ ] Verify early-exit logs exist
