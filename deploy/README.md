# DigitalOcean 1-Droplet Deployment (Docker Compose)

## Suggested Droplet
- Basic Droplet: `$6` or `$8` monthly
- Ubuntu 22.04 LTS
- Add SSH key at create time

## Install Docker
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

## Deploy
```bash
git clone https://github.com/qualitymaterial/Stratum-Sports.git
cd Stratum-Sports
cp .env.example .env
docker compose up -d --build
```

## Logs / Restart
```bash
docker compose ps
docker compose logs -f --tail=200
docker compose restart
docker compose up -d --build
```

## Ports
- Open `8000/tcp` for API access.
- Open frontend/app ports used by your compose stack (for example `3000/tcp`) if needed.

## Firewall Helper
Use `deploy/ufw.sh` to allow SSH + app port and deny other inbound traffic.

## Boot on Restart
Install `deploy/systemd/stratum-compose.service` as a systemd service to auto-start Docker Compose on boot.
