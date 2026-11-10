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

# Database: PostgreSQL
_ENV_DB_NAME = os.getenv('DB_NAME')
_ENV_DB_USER = os.getenv('DB_USER', 'postgres')
_ENV_DB_PASSWORD = os.getenv('DB_PASSWORD')
_ENV_DB_HOST = os.getenv('DB_HOST', 'localhost')
_ENV_DB_PORT = os.getenv('DB_PORT', '5432')

# If DB_PASSWORD is not explicitly provided in environment, probe known environment credentials
if not _ENV_DB_PASSWORD:
    _candidate_passwords = [
        'postgres_secure_pass_2026',
        'postgres',
        'root',
        'rathinam',
        'rathinam@123',
        'nextup',
    ]
    _candidate_dbs = [_ENV_DB_NAME] if _ENV_DB_NAME else ['task_tracker_db', 'nextup_db', 'postgres']
    _candidate_hosts = [_ENV_DB_HOST, '127.0.0.1'] if _ENV_DB_HOST == 'localhost' else [_ENV_DB_HOST]

    try:
        import psycopg2
        _connected = False
        for _h in _candidate_hosts:
            if _connected:
                break
            for _p in _candidate_passwords:
                if _connected:
                    break
                for _d in _candidate_dbs:
                    try:
                        _conn = psycopg2.connect(
                            dbname=_d,
                            user=_ENV_DB_USER,
                            password=_p,
                            host=_h,
                            port=_ENV_DB_PORT,
                            connect_timeout=2
                        )
                        _conn.close()
                        _ENV_DB_PASSWORD = _p
                        _ENV_DB_HOST = _h
                        if not _ENV_DB_NAME:
                            _ENV_DB_NAME = _d
                        _connected = True
                        break
                    except Exception:
                        pass
    except Exception:
        pass

if not _ENV_DB_NAME:
    _ENV_DB_NAME = 'task_tracker_db'
if not _ENV_DB_PASSWORD:
    _ENV_DB_PASSWORD = 'postgres'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _ENV_DB_NAME,
        'USER': _ENV_DB_USER,
        'PASSWORD': _ENV_DB_PASSWORD,
        'HOST': _ENV_DB_HOST,
        'PORT': _ENV_DB_PORT,
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),
    }
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

