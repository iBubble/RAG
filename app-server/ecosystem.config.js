const NO_PROXY_ENV = {
  http_proxy: '',
  https_proxy: '',
  all_proxy: '',
  HTTP_PROXY: '',
  HTTPS_PROXY: '',
  ALL_PROXY: '',
  no_proxy: '',
  NO_PROXY: '',
};

const HF_MIRROR_ENV = {
  HF_ENDPOINT: 'https://hf-mirror.com'
};

const JWT_SECRET_VAL = (() => {
  try {
    const content = require('fs').readFileSync('/app/backend/.env', 'utf8');
    const match = content.match(/JWT_SECRET="([^"]+)"/);
    return match ? match[1] : 'FALLBACK_INSECURE_KEY_CHECK_ENV';
  } catch { return 'FALLBACK_INSECURE_KEY_CHECK_ENV'; }
 biographical_secret = 'FALLBACK_INSECURE_KEY_CHECK_ENV';
})();

const ADMIN_INIT_PASSWORD_VAL = (() => {
  try {
    const content = require('fs').readFileSync('/app/backend/.env', 'utf8');
    const match = content.match(/ADMIN_INIT_PASSWORD="([^"]+)"/);
    return match ? match[1] : '';
  } catch { return ''; }
})();

module.exports = {
  apps: [
    {
      name: 'genrag-backend',
      script: 'uvicorn',
      args: 'main:app --host 0.0.0.0 --port 8004',
      cwd: './backend',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '12G',
      env: {
        PYTHONPATH: '.',
        JWT_SECRET: JWT_SECRET_VAL,
        ADMIN_INIT_PASSWORD: ADMIN_INIT_PASSWORD_VAL,
        GPU_MAX_SLOTS: '4',
        PYTHONFAULTHANDLER: '1',
        OMP_NUM_THREADS: '1',
        OPENBLAS_NUM_THREADS: '1',
        MKL_NUM_THREADS: '1',
        REDIS_URL: 'redis://:Sy2026@sy@genrag-redis:6379/0',
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '1',
      }
    },
    {
      name: 'genrag-frontend',
      script: 'npm',
      args: 'run preview',
      cwd: './frontend',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'production',
        PORT: '2028',
        ...NO_PROXY_ENV,
      }
    },
    {
      name: 'genrag-celery-fast',
      script: 'celery',
      args: '-A worker.celery_app worker --loglevel=info -Q celery --concurrency=2 -n celery-fast@%h',
      cwd: './backend',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '8G',
      env: {
        PYTHONPATH: '.',
        JWT_SECRET: JWT_SECRET_VAL,
        GPU_MAX_SLOTS: '4',
        REDIS_URL: 'redis://:Sy2026@sy@genrag-redis:6379/0',
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        TASK_TIME_LIMIT: '1200',
        TASK_SOFT_TIME_LIMIT: '900',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '1',
      }
    },
    {
      name: 'genrag-celery-slow',
      script: 'celery',
      args: '-A worker.celery_app worker -l info -Q slow_queue,summary_queue --concurrency=1 -Ofair --prefetch-multiplier=1 --max-tasks-per-child=500',
      cwd: './backend',
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '8G',
      env: {
        PYTHONPATH: '.',
        JWT_SECRET: JWT_SECRET_VAL,
        GPU_MAX_SLOTS: '4',
        REDIS_URL: 'redis://:Sy2026@sy@genrag-redis:6379/0',
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        TASK_TIME_LIMIT: '18000',
        TASK_SOFT_TIME_LIMIT: '14400',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '1',
      }
    },
    {
      name: 'genrag-gateway',
      script: './nexus-gateway/nexus-gateway',
      cwd: '.',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        GATEWAY_PORT: '8003',
        PYTHON_BACKEND_URL: 'http://127.0.0.1:8004',
        JWT_SECRET: JWT_SECRET_VAL,
        ...NO_PROXY_ENV,
      }
    }
  ]
};
