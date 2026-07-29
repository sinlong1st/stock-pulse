# Buying a cheap server — a beginner's walkthrough

You want a computer that stays on 24/7 in a data center so StockPulse keeps
running when your laptop is closed. That rented computer is called a **VPS**
(Virtual Private Server) — a slice of a big physical machine, yours to control,
billed by the month (or hour). This guide takes you from "I have nothing" to
"I'm logged into my own server", then hands you to **[DEPLOY.md](DEPLOY.md)** to
install and run the app.

No prior server experience assumed. Take it slow; you can't really break
anything you can't just delete and recreate.

---

## 1. What you're actually buying

A VPS is described by a few numbers. For StockPulse you need very little:

| Spec | What it means | What you need |
|---|---|---|
| **vCPU** | processing cores | **1** is plenty |
| **RAM** | working memory | **1 GB** (2 GB if you want headroom) |
| **Disk (SSD)** | storage | **10–25 GB** is way more than enough |
| **Traffic** | monthly data transfer | any plan's allowance is fine (we use little) |
| **OS** | operating system | **Ubuntu 24.04 LTS** (the standard, well-documented choice) |

This is the **cheapest tier** every provider offers — roughly **$4–6/month**.
The only variable cost on top is your OpenAI usage.

> **Why not just a free tier?** Free/"serverless" hosts sleep when idle. A
> sleeping app misses its 08:30 briefing. You want a small server that's
> *always on* — hence a cheap paid VPS.

---

## 2. Where to buy — recommended providers

All of these are reputable. Prices are approximate (Jul 2026) — check the
current price on their site.

| Provider | Cheapest plan | Best for | Notes |
|---|---|---|---|
| **DigitalOcean** ⭐ | ~$4–6/mo (Basic Droplet) | **Beginners** — best tutorials/UX (your pick) | Often a free credit for new signups |
| **Hetzner** | ~€4/mo (CX22: 2 vCPU / 4 GB) | **Cheapest, great value** | German + US regions; account may need ID verification |
| **Vultr** | ~$5/mo | Many regions incl. US West | Similar to DigitalOcean |
| **Linode (Akamai)** | ~$5/mo (Nanode) | Solid docs | Owned by Akamai now |

**My pick for you: DigitalOcean.** It's the most beginner-friendly — the
cleanest dashboard, an enormous library of step-by-step tutorials, and usually a
signup credit — which matters more than saving a dollar or two while you're
learning. The walkthrough below uses **DigitalOcean**; **Hetzner** is the
cheaper alternative to graduate to once you're comfortable, and I note its
differences inline.

> **Region tip:** pick a data center near *you* (US West, e.g. Hillsboro OR /
> San Francisco) so logging in feels snappy. The app talks to OpenAI/Telegram
> from anywhere, so region isn't critical — pick for your own convenience.

---

## 3. First, make an SSH key (do this before creating the server)

You log into a server with an **SSH key**, not a password — it's a pair of
files: a **private key** (stays secret on your laptop) and a **public key** (you
give this to the server). Think of the public key as a padlock you hand out, and
the private key as the only key that opens it.

On **Windows (PowerShell)** — this is already on your machine:

```powershell
ssh-keygen -t ed25519 -C "stockpulse"
```

- Press **Enter** to accept the default location
  (`C:\Users\Doni\.ssh\id_ed25519`).
- You can set a passphrase (extra protection) or press Enter twice for none.

Now show your **public** key so you can copy it:

```powershell
Get-Content $HOME\.ssh\id_ed25519.pub
```

Copy the whole line (starts with `ssh-ed25519 …`). You'll paste it into the
provider's dashboard in the next step. **Never share the other file**
(`id_ed25519`, without `.pub`) — that's your private key.

---

## 4. Create the server (DigitalOcean)

1. Go to **https://www.digitalocean.com** and **Sign up** (you'll usually get a
   free trial credit). Confirm your email and add a payment method.
2. In the dashboard, click **Create → Droplets**. ("Droplet" is just
   DigitalOcean's word for a VPS.)
3. **Choose Region:** a US-West location closest to California — **San Francisco
   (SFO3)**.
4. **Choose an image:** **Ubuntu 24.04 (LTS) x64**.
5. **Choose Size:** **Basic** → **Regular** (Shared CPU). Pick the **$6/mo**
   option (1 GB RAM / 1 vCPU / 25 GB SSD) — a little headroom for Docker. (The
   $4/mo 512 MB plan can work but is tight.)
6. **Choose Authentication Method:** **SSH Key → Add SSH Key**, paste the public
   key from step 3, name it `my-laptop`, and make sure it's ticked.
7. **Hostname:** `stockpulse`. Leave everything else at its default.
8. Click **Create Droplet**. After ~30–60 seconds it shows a **public IP
   address** (like `164.90.x.x`). Copy it.

> **Prefer Hetzner (cheaper) once you're comfortable?** Sign up at
> **hetzner.com/cloud** → **+ New Project** → **Add Server** → a US location
> (Hillsboro, OR) → **Ubuntu 24.04** → cheapest shared **CX** plan → paste your
> SSH key → **Create & Buy Now**. Same idea, same result: a server with a public
> IP. (Hetzner may ask for one-time ID verification when you first sign up.)

---

## 5. Log into your server for the first time

Back in **PowerShell**, connect (replace with your Droplet's IP):

```powershell
ssh root@164.90.x.x
```

- First time, it asks "Are you sure you want to continue connecting?" — type
  **yes**.
- If you set a key passphrase, enter it.

You're in! The prompt changes to something like `root@stockpulse:~#`. That's a
Linux command line *on your server*. 🎉

**A tiny bit of first-time housekeeping** (optional but good practice):

```bash
# update the system
apt update && apt upgrade -y

# turn on a basic firewall (SSH stays open; nothing else is exposed anyway)
ufw allow OpenSSH
ufw --force enable
```

> StockPulse needs **no inbound ports** — it only makes outbound calls — so you
> don't have to open anything else. You'll reach the dashboard through an SSH
> tunnel, explained in DEPLOY.md.

---

## 6. Now install and run StockPulse

Your server is ready. Continue with **[DEPLOY.md](DEPLOY.md)** from step 2
(*Install Docker*) — it covers installing Docker, cloning the repo, filling in
your keys, and starting the app with `docker compose up -d`.

---

## 7. Managing cost & the server

- **Billing** is usually hourly up to the monthly cap, so a $5/mo server costs
  ~$0.007/hour. Leaving it on all month ≈ the monthly price.
- **To stop paying, you must DELETE (destroy) the server**, not just power it
  off — most providers bill powered-off servers too. Back up your `data/`
  folder first (see DEPLOY.md).
- **Snapshots/backups** (a few cents to a dollar a month) let you restore the
  whole server later — optional.
- Keep your **provider login** and your **SSH private key** safe. Losing the
  private key means you re-add a new public key via the provider console.

---

## Mini-glossary

- **VPS / server / droplet / instance** — all mean the rented always-on computer.
- **IP address** — the server's phone number on the internet (e.g. `5.161.x.x`).
- **SSH** — the secure way you connect to and control the server from your laptop.
- **Ubuntu** — the Linux operating system running on it.
- **Docker** — packages StockPulse so it runs the same everywhere (set up in DEPLOY.md).
- **SSH tunnel** — a private, encrypted link that lets you open the server's
  dashboard in your local browser without exposing it to the world.
