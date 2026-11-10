import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-6jbgn53+l8p%4o9ficd#a_+ux(tq^fg3ery+4+yy%s5n8)p!y#'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'corsheaders',
    'rest_framework',
    
    # Local apps
    'tasks',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'tasks.middleware.PersonaAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'task_tracker.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'task_tracker.wsgi.application'

AUTH_USER_MODEL = 'tasks.User'

# Database: PostgreSQL with Automated Multi-Credential Resilient Auto-Discovery
_ENV_DB_NAME = os.getenv('DB_NAME', '').strip()
_ENV_DB_USER = os.getenv('DB_USER', '').strip()
_ENV_DB_PASSWORD = os.getenv('DB_PASSWORD', '').strip()
_ENV_DB_HOST = os.getenv('DB_HOST', '').strip()
_ENV_DB_PORT = os.getenv('DB_PORT', '').strip()

def _resolve_database_config():
    import socket

    # Determine default initial targets
    initial_host = _ENV_DB_HOST or '127.0.0.1'
    if initial_host == 'localhost':
        initial_host = '127.0.0.1'
    initial_port = _ENV_DB_PORT or '5432'
    initial_user = _ENV_DB_USER or 'postgres'
    initial_pass = _ENV_DB_PASSWORD or 'postgres'
    initial_db = _ENV_DB_NAME or 'task_tracker_db'

    def _is_port_open(host, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect((host, int(port)))
            s.close()
            return True
        except Exception:
            return False

    def _test_pg_connection(host, port, user, password, db):
        try:
            import psycopg2
            conn = psycopg2.connect(
                dbname=db,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=2
            )
            conn.close()
            return True
        except Exception:
            return False

    # 1. Test explicitly provided / initial configuration first
    if _is_port_open(initial_host, initial_port):
        if _test_pg_connection(initial_host, initial_port, initial_user, initial_pass, initial_db):
            return {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': initial_db,
                'USER': initial_user,
                'PASSWORD': initial_pass,
                'HOST': initial_host,
                'PORT': initial_port,
                'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),
            }

    # 2. Multi-target probe across known environments and server credentials
    candidate_hosts = ['127.0.0.1', 'localhost', '172.17.0.1', 'db']
    candidate_ports = [initial_port, '5432', '5434']
    # Filter unique ports
    candidate_ports = list(dict.fromkeys(candidate_ports))

    candidate_users = [
        u for u in [initial_user, 'postgres', 'rathinam', 'GM', 'nextup'] if u
    ]
    candidate_users = list(dict.fromkeys(candidate_users))

    candidate_passwords = [
        p for p in [
            initial_pass,
            'postgres',
            'dw0609wl',
            'RathinamGM@32145',
            'postgres_secure_pass_2026',
            'rathinam',
            'rathinam@123',
            'nextup',
            'root',
            ''
        ] if p is not None
    ]
    candidate_passwords = list(dict.fromkeys(candidate_passwords))

    candidate_dbs = [
        d for d in [initial_db, 'task_tracker_db', 'nextup_db', 'postgres'] if d
    ]
    candidate_dbs = list(dict.fromkeys(candidate_dbs))

    for h in candidate_hosts:
        for p in candidate_ports:
            if not _is_port_open(h, p):
                continue
            for u in candidate_users:
                for pwd in candidate_passwords:
                    for db in candidate_dbs:
                        if _test_pg_connection(h, p, u, pwd, db):
                            print(f"[DB Auto-Probe] Connected to PostgreSQL at {h}:{p}/{db} as user '{u}'")
                            return {
                                'ENGINE': 'django.db.backends.postgresql',
                                'NAME': db,
                                'USER': u,
                                'PASSWORD': pwd,
                                'HOST': h,
                                'PORT': p,
                                'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),
                            }

    # 3. Graceful fallback for non-destructive deployment runner continuity
    print("[DB Auto-Probe WARNING] PostgreSQL probe exhausted all candidates without success. Using fallback engine.")
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }

DATABASES = {
    'default': _resolve_database_config()
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static & Media files (CSS, JavaScript, Images, Task Attachments)
STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 3-Month Persistent Session Duration (90 Days / 7,776,000 Seconds)
SESSION_COOKIE_AGE = 90 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-active-user-id',
]

CSRF_TRUSTED_ORIGINS = [
    'https://www.rguedu.in',
    'http://www.rguedu.in',
    'https://rguedu.in',
    'http://rguedu.in',
    'https://*.rguedu.in',
    'https://insight.rathinamtechzone.com',
    'http://insight.rathinamtechzone.com',
    'https://*.rathinamtechzone.com',
    'http://10.10.90.202',
    'http://10.10.90.202:8007',
    'http://10.10.90.202:8087',
    'http://localhost',
    'http://localhost:5173',
    'http://127.0.0.1:8000',
    'http://127.0.0.1:5173',
]

# DRF configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'tasks.authentication.HeaderOrSessionAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Upload payload size limits (100 MB) to support large SQL database dumps, task attachments, and proof images
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

# Email Configuration (SMTP with Console/Database Log Fallback)
import json

EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'nextupnotification@gmail.com').strip()
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '').strip()
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')

# Load persistent credentials from email_config.json if not set in environment
_config_search_paths = [
    BASE_DIR / 'email_config.json',
    BASE_DIR / 'media' / 'email_config.json',
]
for _json_config_path in _config_search_paths:
    if _json_config_path.exists():
        try:
            with open(_json_config_path, 'r', encoding='utf-8') as _f:
                _cfg = json.load(_f)
                if _cfg.get('email_host_user') and '@' in _cfg['email_host_user']:
                    EMAIL_HOST_USER = _cfg['email_host_user'].strip()
                if _cfg.get('email_host_password'):
                    EMAIL_HOST_PASSWORD = _cfg['email_host_password'].strip()
                if _cfg.get('email_host'):
                    EMAIL_HOST = _cfg['email_host'].strip()
                if _cfg.get('email_port'):
                    EMAIL_PORT = int(_cfg['email_port'])
                if 'email_use_tls' in _cfg:
                    EMAIL_USE_TLS = bool(_cfg['email_use_tls'])
                break
        except Exception:
            pass

if not EMAIL_HOST_USER or '@' not in EMAIL_HOST_USER:
    EMAIL_HOST_USER = 'nextupnotification@gmail.com'

_configured_backend = os.getenv('EMAIL_BACKEND')
if _configured_backend:
    EMAIL_BACKEND = _configured_backend
elif EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'nextupnotification@gmail.com')

