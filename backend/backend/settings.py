import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'platform-template-local-dev-secret-change-me')
_sm4_key_source = os.getenv('SM4_MASTER_KEYS') or os.getenv('SM4_MASTER_KEY') or SECRET_KEY
SM4_MASTER_KEYS = [key.strip() for key in _sm4_key_source.split(',') if key.strip()]
SMS_SECURITY_KEY = os.getenv('SMS_SECURITY_KEY') or SECRET_KEY
DEBUG = os.getenv('DJANGO_DEBUG', 'true').lower() in {'1', 'true', 'yes', 'on'}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver,*').split(',')
    if host.strip()
]
TRUSTED_PROXY_IPS = [
    entry.strip()
    for entry in os.getenv('TRUSTED_PROXY_IPS', '127.0.0.1/32,::1/128').split(',')
    if entry.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'ops.apps.OpsConfig',
    'platform_logs.apps.PlatformLogsConfig',
    'identity',
    'security_frp.apps.SecurityFrpConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'ops.middleware.ApiAuditMiddleware',
]

ROOT_URLCONF = 'backend.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [os.path.join(BASE_DIR, 'templates')],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
FRONT_PUBLIC_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'front', 'public'))
FRONT_DIST_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'front', 'dist'))
MEDIA_URL = '/uploads/'
MEDIA_ROOT = os.path.join(FRONT_PUBLIC_DIR, 'uploads')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

_cors_origins = os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://127.0.0.1:5173,http://localhost:5173,http://192.168.3.172:5173',
)
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in _cors_origins.split(',') if origin.strip()]
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://192.168.3.172:5173']

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['ops.authentication.JWTAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['ops.permissions.RoleBasedPermission'],
    'DEFAULT_PAGINATION_CLASS': 'ops.pagination.StandardPagination',
    'PAGE_SIZE': 100,
    'EXCEPTION_HANDLER': 'ops.exceptions.ongrid_exception_handler',
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'platform-template-login-throttle',
    }
}

ONGRID_ACCESS_TOKEN_MINUTES = int(os.getenv('ONGRID_ACCESS_TOKEN_MINUTES', '30'))
ONGRID_REFRESH_TOKEN_DAYS = int(os.getenv('ONGRID_REFRESH_TOKEN_DAYS', '7'))
PLATFORM_DISPLAY_NAME = os.getenv('PLATFORM_DISPLAY_NAME', '基础平台')
