# Deploying the search app

How to put the API and UI on one small Linux VM with HTTPS. The steps use Azure, but any Ubuntu VM works: skip the `az` commands and open ports 80 and 443 in your provider's firewall instead.

The setup is one process and one proxy:

- `uvicorn` runs the FastAPI app on `127.0.0.1:8000`. It serves both the API (`/api/...`) and the UI (`web/`), so there's no separate frontend host.
- Caddy listens on 80/443, gets a free HTTPS certificate automatically, and forwards everything to uvicorn.
- systemd keeps uvicorn running and restarts it on a crash or a reboot.

## What you need

- A VM with **at least 4 GB of RAM**. The model and the index take about 1 GB once loaded, and installing PyTorch and building the index need more. Azure's `Standard_B2als_v2` (2 vCPU, 4 GB) works.
- Ubuntu 24.04, about 30 GB of disk (the install uses about 6 GB).
- No GPU. Everything runs on CPU.
- A hostname. Azure gives a free one (`<dns-label>.<region>.cloudapp.azure.com`), and Caddy needs one to issue the certificate.

## 1. Create the VM (Azure)

```sh
az group create -n <resource-group> -l <region>
az vm create -g <resource-group> -n <vm-name> --image Ubuntu2404 --size Standard_B2als_v2 \
  --admin-username azureuser --ssh-key-values ~/.ssh/<key>.pub \
  --os-disk-size-gb 30 --storage-sku StandardSSD_LRS --public-ip-sku Standard --nsg-rule NONE

# Web traffic from anywhere, SSH only from your own IP.
az network nsg rule create -g <resource-group> --nsg-name <vm-name>NSG -n web --priority 1010 \
  --access Allow --protocol Tcp --direction Inbound --destination-port-ranges 80 443 --source-address-prefixes Internet
az network nsg rule create -g <resource-group> --nsg-name <vm-name>NSG -n ssh --priority 1000 \
  --access Allow --protocol Tcp --direction Inbound --destination-port-ranges 22 \
  --source-address-prefixes $(curl -s https://api.ipify.org)/32

# Free hostname: <dns-label>.<region>.cloudapp.azure.com
az network public-ip update -g <resource-group> -n <vm-name>PublicIP --dns-name <dns-label>
```

## 2. Install the app

SSH in (`ssh -i ~/.ssh/<key> azureuser@<hostname>`), then:

```sh
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip git
git clone --recurse-submodules https://github.com/jeffgord/cds-capstone.git
cd cds-capstone
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
# CPU-only PyTorch: the VM has no GPU, and the default wheel pulls ~2 GB of CUDA libraries.
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt -r api/requirements.txt
```

Ubuntu 24.04's Python 3.12 works fine.

## 3. Build the index and fetch covers

The index (`gutenberg_faiss_test/`) and covers (`data/raw/covers/`) aren't in git, so build them on the VM. This also downloads the embedding model.

```sh
nohup .venv/bin/python build_index.py > build.log 2>&1 &     # ~40 min on 2 CPU cores, vs ~1 min on a laptop GPU
nohup .venv/bin/python ingestion/download_covers.py > covers.log 2>&1 &   # optional, ~11 min, ~18 MB
```

Using `nohup` keeps them running if SSH drops. To save the 40 minutes, you can build on a laptop and copy the folder over instead: `scp -r gutenberg_faiss_test azureuser@<hostname>:cds-capstone/`. It has to be built with the same model the server uses. Without covers, the UI loads them from gutenberg.org.

Check it before going further:

```sh
.venv/bin/python search_cli.py "peaceful diplomacy without military conflict"
```

## 4. Run it as a service

Create `/etc/systemd/system/cds-search.service`:

```ini
[Unit]
Description=cds-capstone search API and UI
After=network-online.target

[Service]
User=azureuser
WorkingDirectory=/home/azureuser/cds-capstone
# The model was downloaded during build_index.py; skip Hugging Face network checks on start.
Environment=HF_HUB_OFFLINE=1
ExecStart=/home/azureuser/cds-capstone/.venv/bin/uvicorn api.app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now cds-search
curl -s 127.0.0.1:8000/api/health    # "ready": true within a minute, once the model has loaded
```

Search settings (`SEARCH_INDEX_DIR`, `SEARCH_MODEL`, `SEARCH_QUERY_PREFIX`; see [api/README.md](../api/README.md)) go in as more `Environment=` lines.

## 5. HTTPS with Caddy

```sh
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

Replace `/etc/caddy/Caddyfile` with:

```
<hostname> {
	encode gzip
	reverse_proxy 127.0.0.1:8000
}
```

```sh
sudo systemctl reload caddy
curl -s https://<hostname>/api/health
```

Caddy gets and renews the certificate on its own. Ports 80 and 443 have to be open to the internet for that.

## Updating

After new commits land on `main`:

```sh
cd ~/cds-capstone && git pull --ff-only && sudo systemctl restart cds-search
```

Rebuild the index (step 3) only when `data/books/` or what gets embedded changes. Pulling UI or API code needs only the restart. Browsers pick up new UI files without a hard refresh, because the app tells them to revalidate.

If SSH is blocked (for example your IP changed), Azure can run the same command without SSH:

```sh
az vm run-command invoke -g <resource-group> -n <vm-name> --command-id RunShellScript \
  --scripts "cd /home/azureuser/cds-capstone && sudo -u azureuser git pull --ff-only && systemctl restart cds-search"
```

To let your new IP in again, update the `ssh` firewall rule with `--source-address-prefixes $(curl -s https://api.ipify.org)/32`.

## Hosting the UI separately (optional)

The UI is static files, so it can live on a static host (for example Cloudflare Pages) with the API on the VM:

- In `web/config.js`, set `apiBase` to the API's URL, e.g. `"https://<hostname>"`.
- On the VM, allow the UI's origin with `Environment=CORS_ORIGINS=https://<ui-site>` in the service file, then restart.

## Troubleshooting

- **`/api/health` says not ready, or 503 on search.** The model is still loading (up to a minute), or the index folder is missing. Check with `journalctl -u cds-search -n 50`.
- **Caddy has no certificate.** The hostname has to resolve to the VM, and port 80 has to be open. Check with `journalctl -u caddy -n 50`.
- **Killed during `pip install` or `build_index.py`.** Out of memory. Use a VM with 4 GB or more.
- **Slow first search after a restart.** That's normal, the model loads in the background. After that a search takes about 50 ms on 2 CPU cores.

## Cost and shutting down

A 2 vCPU / 4 GB burstable VM runs about $30 a month. When it's not needed:

```sh
az vm deallocate -g <resource-group> -n <vm-name>   # pause: only disk and IP are billed, a few dollars a month
az vm start -g <resource-group> -n <vm-name>        # resume; systemd starts the app again
az group delete -n <resource-group>                 # delete everything
```
