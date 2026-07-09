module.exports = {
  apps: [
    {
      name: "shorts-frontend",
      script: "npm",
      args: "run start",
      cwd: "/root/shorts_cortes_ai/web",
      env: {
        PORT: 3000,
        NODE_ENV: "production"
      }
    }
  ]
};
