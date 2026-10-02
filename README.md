# CyberVault: Secure 2FA Authentication & Project Management System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Flask 3.x](https://img.shields.io/badge/flask-3.x-green.svg)](https://flask.palletsprojects.com/)
[![2FA TOTP RFC 6238](https://img.shields.io/badge/2FA-RFC%206238%20TOTP-cyan.svg)](https://datatracker.ietf.org/doc/html/rfc6238)
[![Tests Passing](https://img.shields.io/badge/tests-22%20passed-brightgreen.svg)]()
[![Security](https://img.shields.io/badge/security-Argon2id%20%7C%20Fernet-purple.svg)]()

CyberVault is an enterprise-grade, high-security web application combining **strict Two-Factor Authentication (2FA)** with a **private project upload and management repository**. Designed with a zero-trust architecture, the system guarantees that no project or dashboard functionality can be accessed without successful multi-factor verification.

---

## 1. System Architecture & Two-Step Verification Flow

```
+-----------------------------------------------------------------------------------+
|                              USER ACCESS WORKFLOW                                 |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [ Step 1: Primary Authentication ]                                              |
|  User enters Identifier (Username/Email) & Password                               |
|        │                                                                          |
|        ▼                                                                          |
|  Argon2id Password Hash Verification                                              |
|        │                                                                          |
|        ├──► Incorrect: Access Denied + Security Audit Log Recorded               |
|        └──► Correct: Restricted Pending State (pending_2fa=True, verified=False)  |
|                                                                                   |
|  [ Step 2: Multi-Factor Authentication ]                                         |
|  User opens Google Authenticator / Microsoft Authenticator                        |
|  Submits 6-Digit TOTP Code (or Emergency Single-Use Recovery Code)                |
|        │                                                                          |
|        ▼                                                                          |
|  Server verifies TOTP against Fernet-encrypted secret at rest                     |
|  + Replay Protection Verification + Time Drift Window Handling                    |
|        │                                                                          |
|        ├──► Invalid/Replayed: 403 Forbidden / Access Blocked                     |
|        └──► Valid: Session Rotation + 2fa_verified=True                           |
|                                                                                   |
|  [ Protected Vault Access Granted ]                                               |
|  Access to Dashboard, Isolated Project Storage, Versioning, and File Management   |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

## 2. Core Security Highlights

* **Argon2id Password Hashing**: Utilizes the memory-hard Argon2id hashing algorithm via `argon2-cffi` to withstand GPU brute-force attacks.
* **Encrypted TOTP Secrets at Rest**: Authenticator secret keys are encrypted before database insertion using symmetric **Fernet (AES-128-CBC + HMAC-SHA256)** encryption.
* **RFC 6238 TOTP Engine**: Full compatibility with **Google Authenticator**, **Microsoft Authenticator**, Authy, and 1Password via standard `otpauth://` QR codes.
* **Replay Attack Mitigation**: Prevents reuse of the same 6-digit TOTP within the same 30-second time window.
* **Single-Use Emergency Recovery Codes**: Generates 8 cryptographically hashed backup codes formatted as `XXXX-XXXX` for account recovery.
* **Sandbox Storage Isolation**: Uploaded project files are stored strictly outside the publicly served static directory (`storage/uploads/user_{id}/`), utilizing randomized UUID filenames to prevent file execution and directory listing.
* **Path Traversal Guards**: Strict resolution checks disallow `../` traversal or escaping the designated user sandbox directory.
* **SHA-256 Checksums**: Cryptographic hashing calculated on upload streams ensures tamper-evident file integrity tracking.
* **Session Management & Revocation**: Real-time session monitoring allowing users to inspect active IP addresses, user agents, and revoke other workstations remotely.
* **Strict Security Headers**: Automatic application of `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, and `Referrer-Policy`.
* **Rate Limiting**: Defends endpoints against brute-force login and OTP guessing using `Flask-Limiter`.

---

## 3. Technology Stack

* **Backend**: Python 3.10+, Flask 3.x, Flask-Login, Flask-WTF, Flask-SQLAlchemy, Flask-Migrate, Flask-Limiter, PyOTP, Cryptography (Fernet), Argon2-cffi, Werkzeug.
* **Frontend**: Responsive Dark Navy Cybersecurity GUI, Bootstrap 5, FontAwesome 6, Modern Glassmorphism CSS, Vanilla ES6 JavaScript.
* **Database**: SQLite (default for development/testing), PostgreSQL (supported in production).
* **Testing**: Pytest, Flask Test Client.
* **Deployment**: Gunicorn, Docker, Docker Compose.

---

## 4. Project Directory Structure

```
secure_project_manager/
├── app/
│   ├── __init__.py            # Application factory, security headers & error handlers
│   ├── config.py              # Environment configuration & security constants
│   ├── extensions.py          # Extension instances (db, login_manager, csrf, limiter)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py            # User model with Argon2 & Fernet TOTP encryption
│   │   ├── project.py         # Project entity & metadata
│   │   ├── project_file.py    # Stored file metadata & SHA-256 checksums
│   │   ├── project_version.py # Version release tracking
│   │   ├── session.py         # Workstation session tracking
│   │   └── audit_log.py       # Tamper-evident security audit trail
│   ├── auth/
│   │   ├── routes.py          # Register, Login, 2FA setup/verify, API routes
│   │   ├── services.py        # Authentication & session services
│   │   ├── totp.py            # QR code generation, TOTP & replay prevention
│   │   └── decorators.py      # Strict 2FA access control decorators
│   ├── projects/
│   │   ├── routes.py          # Project management, upload, download, ZIP archive
│   │   ├── services.py        # Project CRUD & quota validation
│   │   ├── storage.py         # Isolated storage & path traversal protection
│   │   └── validators.py      # File extension, MIME & quota checks
│   ├── dashboard/
│   │   └── routes.py          # Dashboard metrics & overview
│   ├── security/
│   │   └── routes.py          # Profile, password change, session revocation
│   ├── templates/             # Modern cybersecurity Jinja2 templates
│   │   ├── base.html
│   │   ├── landing.html
│   │   ├── register.html
│   │   ├── login.html
│   │   ├── setup_2fa.html
│   │   ├── backup_codes.html
│   │   ├── verify_2fa.html
│   │   ├── dashboard.html
│   │   ├── upload.html
│   │   ├── projects.html
│   │   ├── project_details.html
│   │   ├── profile.html
│   │   ├── security.html
│   │   ├── forgot_password.html
│   │   └── error.html
│   └── static/
│       ├── css/custom.css     # Dark navy & cyan cybersecurity theme
│       └── js/main.js         # Real-time password meter, OTP auto-advance, dropzone
├── migrations/                # Alembic database migrations
├── tests/
│   ├── conftest.py            # Test fixtures & temporary sandboxes
│   ├── test_auth.py           # Registration & login tests
│   ├── test_2fa.py            # TOTP enrollment, verify & replay tests
│   ├── test_projects.py       # Project CRUD & versioning tests
│   ├── test_upload_security.py# Upload safety & traversal prevention tests
│   └── test_authorization.py  # Multi-tenant isolation tests
├── storage/                   # Private upload storage outside static directory
├── .env.example               # Environment variables template
├── requirements.txt           # Python dependencies
├── pytest.ini                 # Pytest configuration
├── run.py                     # Application entry point
├── Dockerfile                 # Container specification
├── docker-compose.yml         # Containerized production stack with PostgreSQL
└── README.md                  # System documentation
```

---

## 5. Local Setup & Installation

### Step 1: Clone and Navigate
```bash
cd secure_project_manager
```

### Step 2: Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Generate secure keys:
```bash
python -c "import secrets; from cryptography.fernet import Fernet; print('SECRET_KEY=' + secrets.token_hex(32)); print('FERNET_KEY=' + Fernet.generate_key().decode())"
```
Place these generated keys into your `.env` file.

### Step 5: Initialize the Database
```bash
flask --app run.py db upgrade
```

### Step 6: Start the Development Server
```bash
python run.py
```
Open your browser and navigate to: **`http://localhost:5000`**

---

## 6. Running Automated Tests

Run the full pytest suite (22 security, auth, 2FA, and storage isolation tests):
```bash
pytest -v
```

---

## 7. RESTful API Reference

All protected endpoints require session authentication with completed 2FA.

### Authentication Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/register` | Register a new user |
| `POST` | `/api/login` | Primary login (username/email + password) |
| `POST` | `/api/2fa/enroll` | Generate TOTP secret & QR code data URI |
| `POST` | `/api/2fa/verify-enrollment` | Verify 6-digit code and activate 2FA |
| `POST` | `/api/2fa/verify-login` | Submit TOTP or backup recovery code |
| `POST` | `/api/logout` | Revoke session and log out |
| `POST` | `/api/password/change` | Change master password (requires current password) |
| `POST` | `/api/password/reset` | Request password reset token |

### Dashboard & Profile Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Metric statistics, storage usage, recent activity |
| `GET` | `/api/profile` | Current user profile |
| `PATCH` | `/api/profile` | Update user profile information |

### Projects Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects belonging to user |
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects/{id}` | Retrieve project details, files, and versions |
| `PATCH` | `/api/projects/{id}` | Update project metadata |
| `DELETE` | `/api/projects/{id}` | Delete project and remove all stored files |
| `GET` | `/api/projects/{id}/files` | List attached project files |
| `POST` | `/api/projects/{id}/files` | Upload file to project (multipart/form-data) |
| `GET` | `/api/projects/{id}/files/{file_id}/download` | Secure file download |
| `POST` | `/api/projects/{id}/versions` | Record a new version release |

### Security Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/security/status` | Current 2FA and session status |
| `POST` | `/api/security/2fa/disable` | Disable 2FA (requires password confirmation) |
| `POST` | `/api/security/2fa/re-enroll` | Unlock 2FA re-enrollment |
| `GET` | `/api/security/sessions` | List active workstation sessions |
| `DELETE` | `/api/security/sessions/{id}` | Revoke a specific workstation session |
| `GET` | `/api/security/activity` | Retrieve account security audit logs |

---

## 8. Production Deployment

### Option A: Docker Compose with PostgreSQL
```bash
docker compose up -d --build
```
This boots both the fortified Flask application on port `5000` with Gunicorn and an isolated PostgreSQL 16 database.

### Option B: Standalone Production with Gunicorn & Nginx
```bash
pip install gunicorn
gunicorn --bind 127.0.0.1:5000 --workers 4 --threads 2 --worker-class gthread run:app
```

Configure Nginx reverse proxy with HTTPS / TLS:
```nginx
server {
    listen 443 ssl http2;
    server_name vault.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/vault.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vault.yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```
Set `SESSION_COOKIE_SECURE=True` in `.env` when running under HTTPS.
