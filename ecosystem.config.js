// PM2: pm2 start ecosystem.config.js && pm2 save
// Started through `env -i` so the API gets ONLY the variables below: PM2 otherwise passes the
// launching shell's environment (tokens, etc.) and its own config keys (env, name, ...) to the app.
const ENV = {
  PATH: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
  HOME: "/root",
  LANG: "C.UTF-8",
  PYTHONUNBUFFERED: "1",
  OMP_NUM_THREADS: "4",
  HF_HUB_OFFLINE: "1", // model + voices are pre-downloaded; startup never depends on huggingface.co
};

module.exports = {
  apps: [
    {
      name: "voice-api",
      cwd: "/www/aiwazz/api",
      script: "/usr/bin/env",
      // One worker only: the model (1.3 GB) and the single-synthesis queue live in this process.
      args: [
        "-i",
        ...Object.entries(ENV).map(([k, v]) => `${k}=${v}`),
        "/www/aiwazz/api/.venv/bin/uvicorn", "main:app",
        "--host", "127.0.0.1", "--port", "8100", "--workers", "1",
        "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1", "--no-server-header",
      ],
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      min_uptime: "30s",
      restart_delay: 3000,
      kill_timeout: 10000,
      max_memory_restart: "3500M",
      out_file: "/www/aiwazz/api/storage/logs/voice-api.out.log",
      error_file: "/www/aiwazz/api/storage/logs/voice-api.err.log",
      time: true,
    },
  ],
};
