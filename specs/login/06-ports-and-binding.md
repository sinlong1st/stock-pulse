# 06 — Ports and binding

## The problem

A server has one IP address but runs many programs. When a packet arrives, which
program gets it?

And a second, sharper question for us: your droplet runs a FastAPI app with
eleven unauthenticated routes, on a machine with a public IP, connected to the
internet. Why is that not already a catastrophe?

The answer is one line of configuration, and it is worth understanding exactly.

## The idea

A **port** is a number (0–65535) that identifies which program on a machine a
connection is for. An address is really `IP : port`.

| Port | Usually |
|---|---|
| 22 | SSH |
| 80 | HTTP |
| 443 | HTTPS |
| 8000 | whatever you're developing (uvicorn's habit) |

When a program starts listening, it **binds** to an address and port. The address
half is the part people skim, and it decides everything:

```
  bind 127.0.0.1:8000   ← "only connections originating on THIS machine"
  bind 0.0.0.0:8000     ← "connections from ANY network interface"
```

`127.0.0.1` (**localhost**, the loopback interface) is a virtual network that
never touches a cable. Packets to it cannot arrive from outside — the kernel will
not route them there. It is not a firewall rule that could be misconfigured; it
is a property of the interface.

```
   ┌──────────────── droplet ────────────────┐
   │                                          │
   │  loopback 127.0.0.1   ← unreachable from outside, ever
   │     └── your app :8000                   │
   │                                          │
   │  public eth0 164.90.х.х  ← the internet can reach this
   │     ├── sshd :22                         │
   │     └── (nothing else, today)            │
   │                                          │
   └──────────────────────────────────────────┘
```

## In StockPulse — the line that is saving you

`docker-compose.yml`:

```yaml
    ports:
      # Bound to localhost only — reach the dashboard via an SSH tunnel:
      #   ssh -L 8000:127.0.0.1:8000 user@your-server
      - "127.0.0.1:8000:8000"
```

That `127.0.0.1:` prefix is the reason `POST /run` is not currently an anonymous
button on the internet. Delete those nine characters and every unauthenticated
route in file 01 becomes public immediately.

Docker makes this especially easy to get wrong: `- "8000:8000"` — the form in most
tutorials — binds to **all** interfaces. Worse, Docker writes its own iptables
rules, so a published port can bypass a UFW rule you thought was protecting you.
People have exposed databases this way while looking at a firewall that said
"deny".

### How you reach it today

Two ways, neither of them public:

- **Tailscale** — the phone is on the private network, so `127.0.0.1` on the
  droplet is reachable via Tailscale's own interface.
- **SSH tunnel** — `ssh -L 8000:127.0.0.1:8000 user@droplet` forwards your
  laptop's port 8000 through the SSH connection. The dashboard then appears at
  `http://localhost:8000` in your browser. Nothing is exposed; SSH already
  authenticated you.

That second one is worth remembering: it is the honest answer for the HTML
dashboards (`/`, `/alerts`, `/evaluation`) even after going public. They are
developer tools; they can stay on localhost forever and you reach them with a
tunnel when you actually need them.

### After the change

```
   Internet ──► :443 Caddy ──► 127.0.0.1:8000 app
                :80  Caddy (redirect + ACME challenge)
                :22  sshd
```

The app **stays** bound to localhost. Caddy is on the same machine, so it can
reach it; nobody else can. Only Caddy is exposed, and Caddy's job is to be
exposed.

## Firewalls, briefly

A firewall (`ufw` on Ubuntu) is a second layer: even if something binds to
`0.0.0.0` by accident, the firewall can refuse the connection.

```bash
sudo ufw default deny incoming
sudo ufw allow 22        # don't lock yourself out — do this FIRST
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

Two independent controls doing the same job is not redundancy for its own sake —
it is defence in depth. Binding is the guarantee; the firewall is the safety net
for the day someone changes the binding without thinking.

**The Docker caveat again:** Docker's published ports insert iptables rules that
can sidestep ufw. The reliable protection for a container is the bind address,
not the firewall.

## Misconceptions

**"Port 8000 is obscure, nobody will find it."** A full scan of all 65,535 ports
on one host takes seconds. Every port is found, constantly. There are no unusual
ports, only unusual expectations.

**"My firewall protects my Docker container."** Often not — Docker manipulates
iptables directly and can bypass ufw rules. Bind to `127.0.0.1` and stop relying
on the firewall for containers.

**"Binding to 0.0.0.0 is fine, the app has auth."** It may be, but you have just
moved a guarantee into an assumption. Bind narrowly and let auth be the *second*
layer, not the only one.

**"localhost and 127.0.0.1 are different things."** Same thing; `localhost` is a
name that resolves to `127.0.0.1` (and `::1` on IPv6 — which occasionally matters
when something binds to one and connects to the other).

## Remember this

- An address is `IP : port`, and **the IP half of a bind decides who can reach
  you**.
- `127.0.0.1:8000:8000` in your compose file is currently doing more for your
  security than anything in your code.
- Keep the app on localhost forever. Expose only the proxy.
