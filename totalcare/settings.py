import os
from pathlib import Path
from decouple import config
import dj_database_url
from dotenv import load_dotenv

# Load environment variables (for local dev)
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY SETTINGS
SECRET_KEY = config('SECRET_KEY', default='your-dev-secret-key')
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

# APPLICATIONS
INSTALLED_APPS = [
    'billing',
    'channels',
    'messaging',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
]


ASGI_APPLICATION = "totalcare.asgi.application"

# For now we’ll use in-memory channel layer (sufficient for dev)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # For static files on Heroku
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URL and WSGI
ROOT_URLCONF = 'totalcare.urls'
WSGI_APPLICATION = 'totalcare.wsgi.application'

# TEMPLATES
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "billing.context_processors.unread_messages",  
            ],
        },
    },
]
# DATABASE CONFIGURATION
if os.environ.get("RENDER") and os.name != 'nt':
    # Production (Render / Supabase / PostgreSQL)
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ.get("DATABASE_URL")
        )
    }
else:
    # Local development (SQLite)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(BASE_DIR, "db.sqlite3"),
        }
    }

# PASSWORD VALIDATION
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# LOCALIZATION
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# STATIC FILES
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Where collectstatic puts files
STATICFILES_DIRS = [BASE_DIR / 'static']  # Where Django looks for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# CUSTOM USER
AUTH_USER_MODEL = 'billing.CustomUser'

# LOGIN / LOGOUT REDIRECTS
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'   # Or your main dashboard
LOGOUT_REDIRECT_URL = '/'

# EMAIL SETTINGS
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='your_email@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='your_app_password')

# AUTO FIELD
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# LOGGING
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

VITAL_ALERT_ESCALATION_RULES = {
    1: {"minutes": 10, "role": "head_doctor"},
    2: {"minutes": 20, "role": "admin"},
}