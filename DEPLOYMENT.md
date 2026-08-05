\# Production Deployment Guide



\## FastAPI Production API



Deployment architecture:



```

Nginx

&#x20;|

Gunicorn

&#x20;|

FastAPI

&#x20;|

PostgreSQL

```



\---



\# 1. Server Requirements



Recommended:



\- Ubuntu 22.04 / 24.04

\- Python 3.13+

\- PostgreSQL

\- Nginx

\- Git

\- uv package manager





\---



\# 2. Clone Repository



```bash

git clone https://github.com/HoungDev/fastapi-production-api.git



cd fastapi-production-api

```



\---



\# 3. Install uv



```bash

curl -LsSf https://astral.sh/uv/install.sh | sh

```



Reload shell:



```bash

source \~/.bashrc

```



\---



\# 4. Install Dependencies



```bash

uv sync

```



\---



\# 5. Configure Environment



Create:



```bash

cp .env.production.example .env

```



Edit:



```bash

nano .env

```



Required:



```env

ENVIRONMENT=production



DEBUG=false



DATABASE\_URL=postgresql+psycopg://user:password@localhost/database



SECRET\_KEY=your-secret-key

```



\---



\# 6. Database Migration



Run:



```bash

uv run alembic upgrade head

```



\---



\# 7. Test Application



Run:



```bash

uv run pytest

```



\---



\# 8. Test Gunicorn



Run:



```bash

uv run gunicorn \\

\-c gunicorn.conf.py \\

src.app.main:app

```



Test:



```

http://server-ip:8000/health

```



\---



\# 9. Systemd Service



Create:



```bash

sudo nano /etc/systemd/system/fastapi.service

```



Example:



```ini

\[Unit]

Description=FastAPI Production API

After=network.target





\[Service]



User=ubuntu



WorkingDirectory=/home/ubuntu/fastapi-production-api



ExecStart=/home/ubuntu/.local/bin/uv run gunicorn \\

\-c gunicorn.conf.py \\

src.app.main:app



Restart=always





\[Install]



WantedBy=multi-user.target

```



Enable:



```bash

sudo systemctl daemon-reload



sudo systemctl enable fastapi



sudo systemctl start fastapi

```



Check:



```bash

sudo systemctl status fastapi

```



\---



\# 10. Nginx Reverse Proxy



Install:



```bash

sudo apt install nginx

```



Configuration:



```nginx

server {



&#x20;   listen 80;



&#x20;   server\_name your-domain.com;





&#x20;   location / {



&#x20;       proxy\_pass http://127.0.0.1:8000;



&#x20;       proxy\_set\_header Host $host;



&#x20;       proxy\_set\_header X-Real-IP $remote\_addr;



&#x20;       proxy\_set\_header X-Forwarded-For $proxy\_add\_x\_forwarded\_for;



&#x20;   }

}

```



Reload:



```bash

sudo nginx -t



sudo systemctl reload nginx

```



\---



\# 11. HTTPS



Install Certbot:



```bash

sudo apt install certbot python3-certbot-nginx

```



Enable SSL:



```bash

sudo certbot --nginx

```



\---



\# 12. Logs



Application logs:



```bash

journalctl -u fastapi -f

```



Nginx logs:



```bash

tail -f /var/log/nginx/access.log

```



\---



\# 13. Deployment Checklist



Completed:



\[x] Environment configuration



\[x] PostgreSQL connection



\[x] Alembic migration



\[x] Gunicorn configuration



\[x] Systemd service



\[x] Nginx reverse proxy



\[x] HTTPS



\[x] Logging





Future improvements:



\- Monitoring

\- Metrics

\- Automated backups

\- Alerting



