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

// WHY: 从 .env 统一读取敏感凭据，禁止在代码中硬编码密码
const dotenv = (() => {
  try {
    const content = require('fs').readFileSync('/app/backend/.env', 'utf8');
    const parse = (key) => {
      const m = content.match(new RegExp(key + '="([^"]+)"'));
      return m ? m[1] : '';
    };
    return {
      JWT_SECRET:      parse('JWT_SECRET')      || 'FALLBACK_INSECURE_KEY_CHECK_ENV',
      ADMIN_INIT_PWD:  parse('ADMIN_INIT_PASSWORD'),
      REDIS_PASSWORD:  parse('REDIS_PASSWORD')   || 'FALLBACK_REDIS_PWD',
      NEO4J_PASSWORD:  parse('NEO4J_PASSWORD')   || '',
    };
  } catch {
    return {
      JWT_SECRET: 'FALLBACK_INSECURE_KEY_CHECK_ENV',
      ADMIN_INIT_PWD: '',
      REDIS_PASSWORD: 'FALLBACK_REDIS_PWD',
      NEO4J_PASSWORD: '',
    };
  }
})();

const JWT_SECRET_VAL       = dotenv.JWT_SECRET;
const ADMIN_INIT_PASSWORD_VAL = dotenv.ADMIN_INIT_PWD;
const REDIS_URL_VAL        = `redis://:${dotenv.REDIS_PASSWORD}@genrag-redis:6379/0`;

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
        REDIS_URL: REDIS_URL_VAL,
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        ASR_MODEL: 'openai/whisper-base',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '0',
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
        GPU_MAX_SLOTS: '1',
        OMP_NUM_THREADS: '1',
        OPENBLAS_NUM_THREADS: '1',
        MKL_NUM_THREADS: '1',
        OMP_WAIT_POLICY: 'PASSIVE',
        REDIS_URL: REDIS_URL_VAL,
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        ASR_MODEL: 'openai/whisper-base',
        TASK_TIME_LIMIT: '1200',
        TASK_SOFT_TIME_LIMIT: '900',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '0',
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
        GPU_MAX_SLOTS: '1',
        OMP_NUM_THREADS: '1',
        OPENBLAS_NUM_THREADS: '1',
        MKL_NUM_THREADS: '1',
        OMP_WAIT_POLICY: 'PASSIVE',
        REDIS_URL: REDIS_URL_VAL,
        QDRANT_URL: 'http://genrag-database:6333',
        VISION_MODEL: 'qwen2.5vl:7b',
        ASR_MODEL: 'openai/whisper-base',
        TASK_TIME_LIMIT: '18000',
        TASK_SOFT_TIME_LIMIT: '14400',
        ...NO_PROXY_ENV,
        ...HF_MIRROR_ENV,
        HF_HUB_OFFLINE: '0',
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
    },
    {
      name: 'genrag-learning-watchdog',
      script: 'python3',
      args: 'scripts/daemon_watchdog.py',
      cwd: './backend',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONPATH: '.',
        JWT_SECRET: JWT_SECRET_VAL,
        REDIS_URL: REDIS_URL_VAL,
        QDRANT_URL: 'http://genrag-database:6333',
        ...NO_PROXY_ENV,
      }
    }
  ]
};
