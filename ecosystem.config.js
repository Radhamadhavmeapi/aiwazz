// PM2: pm2 start ecosystem.config.js && pm2 save
module.exports = {
  apps: [
    {
      name: "voice-api",
      cwd: "/www/aiwazz/api",
      script: ".venv/bin/uvicorn",
      // One worker only: the model (1.3 GB) and the single-synthesis queue live in this process.
      args: "main:app --host 127.0.0.1 --port 8100 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      min_uptime: "30s",
      restart_delay: 3000,
      kill_timeout: 10000,
      max_memory_restart: "3500M",
      // HF_HUB_OFFLINE: model + voices are pre-downloaded; startup never depends on huggingface.co.
      env: { PYTHONUNBUFFERED: "1", OMP_NUM_THREADS: "4", HF_HUB_OFFLINE: "1" },
      out_file: "/www/aiwazz/api/storage/logs/voice-api.out.log",
      error_file: "/www/aiwazz/api/storage/logs/voice-api.err.log",
      time: true,
    },
  ],
};
