# 🗺️ Hybrid Cloud & Edge GitOps Architecture
> **The Big Picture: Decoupled Control, Private Data Sovereignty & Edge Autonomy**

This blueprint defines the final target state of our distributed infrastructure. It details the separation between our **Cloud Gateway Plane** (Cloud VPS), our **Cloud Control Plane** (Management), and our **Local Edge Planes** (Location 1 & Location 2) running Kubernetes on Proxmox.

---

## 🏛️ Comprehensive Architecture Diagram

```text
                                 [ CLOUDFLARE ANYCAST EDGE ]
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼ (HTTPS / SMTP)                                ▼ (UDP 51820)
         ┌───────────────────────────┐                  ┌───────────────────────────┐
         │  VPS 1: Edge Proxy & IPS  │                  │   WireGuard VPN Transit   │
         │ (Nginx, CrowdSec, UFW)    │                  │       (10.8.0.1/24)       │
         └────────────┬──────────────┘                  └─────────────┬─────────────┘
                      │                                               │
                      ▼ (Secure Routing through WireGuard Mesh)       │
         ┌───────────────────────────┐                                │
         │   VPS 2: Cloud Control    │◄───────────────────────────────┤
         │ (Omada Controller,        │                                │
         │  SMTP Relay Gateway)      │                                │
         └───────────────────────────┘                                │
                                                                      │
                      ┌───────────────────────────────────────────────┴───────────────────────────────┐
                      ▼ (WireGuard Site-to-Site LAN Transit)                                          ▼ (WireGuard Site-to-Site LAN Transit)
        ┌───────────────────────────────────────────┐                                   ┌───────────────────────────────────────────┐
        │       Location 1 Node (Site A)            │                                   │       Location 2 Node (Site B)            │
        │       Subnet: 192.168.10.0/24             │                                   │       Subnet: 192.168.20.0/24             │
        ├───────────────────────────────────────────┤                                   ├───────────────────────────────────────────┤
        │  [Physical Proxmox VE Cluster]            │                                   │  [Physical Proxmox VE Edge Node]          │
        │    ┌─────────────────────────────────┐    │                                   │    ┌─────────────────────────────────┐    │
        │    │  Kubernetes (K8s) Cluster       │    │                                   │    │  Kubernetes (K8s) Cluster       │    │
        │    │  (Deployments managed via Git)  │    │                                   │    │  (Deployments managed via Git)  │    │
        │    ├─────────────────────────────────┤    │                                   │    ├─────────────────────────────────┤    │
        │    │  - Mailcow Backend (Mailboxes)  │    │                                   │    │  - Home Assistant L2 (Local HA) │    │
        │    │  - Nextcloud Core & Databases   │    │                                   │    │  - Local MQTT & Node-RED        │    │
        │    │  - Home Assistant L1 (Local HA) │    │                                   │    │  - Frigate NVR (AI Object Det.) │    │
        │    │  - GitLab / Gitea Runner        │    │                                   │    │  - Local Caching & Sync Agent   │    │
        │    └─────────────────────────────────┘    │                                   │    └─────────────────────────────────┘    │
        └───────────────────────────────────────────┘                                   └───────────────────────────────────────────┘
```

---

## ✉️ 1. The Secure Mail Architecture (Cloud SMTP-Relay ➔ Local Mailbox)
Operating a mail server directly from a home connection fails due to dynamic IPs, lack of PTR (Reverse DNS) configuration, and IP blocks on global spam lists. However, hosting your mailboxes in the cloud compromises data privacy. 

We solve this using a **Split SMTP Architecture**:

### Inbound E-Mail Flow:
1.  An external server sends an email to `user@yourdomain.com`.
2.  The DNS MX-record routing points to **VPS 2 (Cloud Control & Mail Relay)**.
3.  The Cloud Relay receives the email on Port `25` (secured with TLS/DKIM checks).
4.  The VPS immediately forwards the email **through the secure WireGuard tunnel** to the local **Mailcow Instance** running inside your **Kubernetes Cluster in Location 1** (`10.8.0.2` or internal routed IP).
5.  The mail is stored on your own physical disks in Site A.

---

## ☸️ 2. The Role of Kubernetes on Proxmox (Location 1 & Location 2)
Running Kubernetes (via a lightweight distro like **k3s** or **Talos Linux**) on Proxmox VE provides cloud-native scaling, self-healing, and GitOps workflows.

### 🇩🇪 Location 1 Cluster (Site A Core) — Datacenter Class
* **Mailcow Backend VMs:** Holding Dovecot, Postfix, and Mailbox databases.
* **Nextcloud Instance:** Connected to your high-capacity local RAID storage.
* **Central Databases:** Highly-available clustered database engines (Postgres, MariaDB).
* **Home Assistant L1 (Core instance):** Interacting with your local smart home appliances.

### 🇰🇪 Location 2 Cluster (Site B Edge) — Heavy-Duty Autonomy
* **Home Assistant L2 (Edge instance):** Operates all local smart devices, smart locks, and localized automated flows. *If the fiber connection to the VPS cuts out, the house continues to work autonomously.*
* **Frigate NVR (Network Video Recorder):** Video processing is highly resource-intensive. Running this locally on the K8s cluster keeps massive video bandwidth off your internet connection.