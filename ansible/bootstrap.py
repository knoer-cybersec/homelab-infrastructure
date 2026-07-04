import os

# 1. Zielverzeichnisse auf deinem Mac definieren
BASE_DIR = os.path.expanduser("~/src/schaufenster")
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
OBSIDIAN_DIR = os.path.join(BASE_DIR, "obsidian_vault")

# Verzeichnisse erstellen
os.makedirs(ANSIBLE_DIR, exist_ok=True)
os.makedirs(OBSIDIAN_DIR, exist_ok=True)

# 2. Definition der Ansible-Dateien
ANSIBLE_FILES = {
    "ansible.asvars": """# Secure Local Ansible variables (YAML-Syntax)
# Trage hier deinen Cloudflare API-Token ein
cloudflare_api_token: "DEIN_CLOUDFLARE_API_TOKEN"
""",

    "nginx_proxy.yml": """---
- name: Deploy Nginx Reverse Proxy mit Cloudflare Wildcard SSL und CrowdSec L7 IPS
  hosts: edge_nodes
  gather_facts: true
  become: true
  
  vars_files:
    - ansible.asvars

  vars:
    admin_user: ansible_admin

  tasks:
    - name: Ueberpruefe ob der Cloudflare API-Token geladen wurde
      ansible.builtin.fail:
        msg: "FEHLER: Der Cloudflare API-Token ist leer! Bitte fuelle 'cloudflare_api_token' in deiner lokalen 'ansible.asvars' aus."
      when: cloudflare_api_token is undefined or cloudflare_api_token | length == 0
      delegate_to: localhost
      become: false

    - name: Installiere Nginx, Certbot und die benoetigten DNS-Plugins
      ansible.builtin.apt:
        name:
          - nginx
          - certbot
          - python3-certbot-nginx
          - python3-certbot-dns-cloudflare
          - crowdsec-nginx-bouncer
        state: present
        update_cache: yes

    - name: Stelle sicher, dass das Let's Encrypt Konfigurationsverzeichnis existiert
      ansible.builtin.file:
        path: /etc/letsencrypt
        state: directory
        mode: '0700'
        owner: root
        group: root

    - name: Schreibe die Cloudflare API-Zugangsdaten mit restriktiven Rechten
      ansible.builtin.copy:
        dest: /etc/letsencrypt/cloudflare.ini
        owner: root
        group: root
        mode: '0600'
        content: |
          # Cloudflare API-Token fuer die DNS-01 Challenge
          dns_cloudflare_api_token = "{{ cloudflare_api_token }}"

    - name: Registriere den Nginx Web-Bouncer in der lokalen CrowdSec-Engine
      ansible.builtin.shell: |
        cscli bouncers add nginx-bouncer || true
      register: bouncer_register_output
      changed_when: "'Api key' in bouncer_register_output.stdout"

    - name: Extrahiere den CrowdSec API-Key und trage ihn in den Nginx-Bouncer ein
      ansible.builtin.shell: |
        KEY=$(echo "{{ bouncer_register_output.stdout }}" | grep -oP "API Key: \\K\\w+")
        if [ ! -z "$KEY" ]; then
          sed -i "s/API_KEY=.*/API_KEY=$KEY/" /etc/crowdsec/bouncers/crowdsec-nginx-bouncer.conf
        fi
      when: bouncer_register_output.changed

    - name: Konfiguriere den korrekten CrowdSec-Local-API-Endpoint im Bouncer
      ansible.builtin.lineinfile:
        path: /etc/crowdsec/bouncers/crowdsec-nginx-bouncer.conf
        regexp: '^API_URL='
        line: 'API_URL=http://127.0.0.1:8080'
        state: present

    - name: Erstelle gehaertete globale SSL-Parameter (Mozilla Modern Profile)
      ansible.builtin.copy:
        dest: /etc/nginx/conf.d/ssl-global.conf
        owner: root
        group: root
        mode: '0644'
        content: |
          # Moderne TLS-Sicherheitslinie
          ssl_protocols TLSv1.2 TLSv1.3;
          ssl_prefer_server_ciphers on;
          ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
          
          # Performance-Optimierung fuer Reverse-Proxy-Betrieb
          ssl_session_cache shared:SSL:10m;
          ssl_session_timeout 1d;
          ssl_session_tickets off;
          
          # HSTS (HTTP Strict Transport Security) - Erzwinge HTTPS fuer 1 Jahr
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
          
          # Schutz vor Clickjacking & Cross-Site Scripting (XSS)
          add_header X-Frame-Options DENY always;
          add_header X-Content-Type-Options nosniff always;
          add_header X-XSS-Protection "1; mode=block" always;
      notify: Reload Nginx

    - name: Oeffne die Ports 80 und 443 in der lokalen UFW-Firewall
      community.general.ufw:
        rule: allow
        port: "{{ item }}"
        proto: tcp
      loop:
        - "80"
        - "443"

    - name: Stelle sicher, dass Nginx aktiv ist und beim Booten startet
      ansible.builtin.systemd:
        name: nginx
        enabled: yes
        state: started

  handlers:
    - name: Reload Nginx
      ansible.builtin.systemd:
        name: nginx
        state: reloaded
""",

    "wireguard.yml": """---
- name: Install and configure WireGuard VPN Hub
  hosts: edge_nodes
  gather_facts: true
  become: true
  vars:
    vpn_network: "10.8.0.0/24"
    vpn_port: 51820
    server_ip: "10.8.0.1/24"
    germany_01_ip: "10.8.0.2/32"
    kenya_01_ip: "10.8.0.3/32"
    admin_01_ip: "10.8.0.4/32"
    germany_01_lan: "192.168.10.0/24"
    kenya_01_lan: "192.168.20.0/24"

  tasks:
    - name: Install WireGuard and routing tools
      ansible.builtin.apt:
        name:
          - wireguard
          - iptables
          - resolvconf
        state: present
        update_cache: yes

    - name: Create WireGuard directory with secure permissions
      ansible.builtin.file:
        path: /etc/wireguard
        state: directory
        mode: '0700'
        owner: root
        group: root

    # --- KEY GENERATION (Idempotent) ---

    - name: Check if server keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/server.key
      register: server_key_state

    - name: Generate server key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
      when: not server_key_state.stat.exists
      changed_when: true

    - name: Check if Germany 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/germany_01.key
      register: germany_01_key_state

    - name: Generate Germany 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/germany_01.key | wg pubkey > /etc/wireguard/germany_01.pub
      when: not germany_01_key_state.stat.exists
      changed_when: true

    - name: Check if Kenya 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/kenya_01.key
      register: kenya_01_key_state

    - name: Generate Kenya 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/kenya_01.key | wg pubkey > /etc/wireguard/kenya_01.pub
      when: not kenya_01_key_state.stat.exists
      changed_when: true

    - name: Check if Admin 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/admin_01.key
      register: admin_01_key_state

    - name: Generate Admin 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/admin_01.key | wg pubkey > /etc/wireguard/admin_01.pub
      when: not admin_01_key_state.stat.exists
      changed_when: true

    # --- READ KEYS ---

    - name: Slurp keys into Ansible variables
      ansible.builtin.slurp:
        src: "/etc/wireguard/{{ item }}"
      register: wg_keys
      loop:
        - server.key
        - server.pub
        - germany_01.key
        - germany_01.pub
        - kenya_01.key
        - kenya_01.pub
        - admin_01.key
        - admin_01.pub

    - name: Assign key variables
      ansible.builtin.set_fact:
        server_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.key') | first).content | b64decode | trim }}"
        server_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.pub') | first).content | b64decode | trim }}"
        germany_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'germany_01.key') | first).content | b64decode | trim }}"
        germany_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'germany_01.pub') | first).content | b64decode | trim }}"
        kenya_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'kenya_01.key') | first).content | b64decode | trim }}"
        kenya_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'kenya_01.pub') | first).content | b64decode | trim }}"
        admin_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'admin_01.key') | first).content | b64decode | trim }}"
        admin_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'admin_01.pub') | first).content | b64decode | trim }}"

    # --- NETWORK & ROUTING CONFIGURATION ---

    - name: Enable IPv4 packet forwarding in kernel (Sysctl)
      ansible.posix.sysctl:
        name: net.ipv4.ip_forward
        value: '1'
        sysctl_set: yes
        state: present
        reload: yes

    - name: Write WireGuard server configuration (wg0.conf)
      ansible.copy:
        dest: /etc/wireguard/wg0.conf
        owner: root
        group: root
        mode: '0600'
        content: |
          [Interface]
          Address = {{ server_ip }}
          ListenPort = {{ vpn_port }}
          PrivateKey = {{ server_private_key }}
          
          # Routing & NAT masquerading on interface start/stop (Fixed: Added internal mesh routing)
          PostUp = ufw route allow in on wg0 out on eth0
          PostUp = ufw route allow in on wg0 out on wg0
          PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
          PostDown = ufw route delete allow in on wg0 out on eth0
          PostDown = ufw route delete allow in on wg0 out on wg0
          PostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

          # Client Peer 1: Germany Omada Gateway
          [Peer]
          PublicKey = {{ germany_01_public_key }}
          AllowedIPs = {{ germany_01_ip }}, {{ germany_01_lan }}

          # Client Peer 2: Kenya Omada Gateway
          [Peer]
          PublicKey = {{ kenya_01_public_key }}
          AllowedIPs = {{ kenya_01_ip }}, {{ kenya_01_lan }}

          # Client Peer 3: Admin 01 (MacBook)
          [Peer]
          PublicKey = {{ admin_01_public_key }}
          AllowedIPs = {{ admin_01_ip }}
      notify: Restart WireGuard

    # --- GENERATE CLIENT CONFIGURATIONS ---

    - name: Create directory for client configurations
      ansible.builtin.file:
        path: /etc/wireguard/clients
        state: directory
        mode: '0700'
        owner: root
        group: root

    - name: Generate Germany 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-germany-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ germany_01_private_key }}
          Address = 10.8.0.2/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ kenya_01_lan }}
          PersistentKeepalive = 25

    - name: Generate Kenya 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-kenya-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ kenya_01_private_key }}
          Address = 10.8.0.3/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ germany_01_lan }}
          PersistentKeepalive = 25

    - name: Generate Admin 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-admin-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ admin_01_private_key }}
          Address = 10.8.0.4/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ germany_01_lan }}, {{ kenya_01_lan }}
          PersistentKeepalive = 25

    # --- SERVICE START ---

    - name: Allow WireGuard port in local UFW firewall
      community.general.ufw:
        rule: allow
        port: "{{ vpn_port | string }}"
        proto: udp

    - name: Enable and start WireGuard Systemd service
      ansible.builtin.systemd:
        name: wg-quick@wg0
        enabled: yes
        state: started

  handlers:
    - name: Restart WireGuard
      ansible.builtin.systemd:
        name: wg-quick@wg0
        state: restarted
""",

    "crowdsec.yml": """---
- name: Install and configure CrowdSec IDS/IPS
  hosts: edge_nodes
  gather_facts: true
  become: true

  tasks:
    - name: Ensure prerequisites are installed
      ansible.builtin.apt:
        name:
          - curl
          - gnupg
          - apt-transport-https
        state: present
        update_cache: yes

    - name: Create secure directory for apt keyrings
      ansible.builtin.file:
        path: /etc/apt/keyrings
        state: directory
        mode: '0755'

    - name: Retrieve official CrowdSec GPG signing key
      ansible.builtin.get_url:
        url: https://packagecloud.io/crowdsec/crowdsec/gpgkey
        dest: /etc/apt/keyrings/crowdsec.asc
        mode: '0644'

    - name: Register CrowdSec stable repository (deb822 format)
      ansible.builtin.deb822_repository:
        name: crowdsec
        types: deb
        uris: https://packagecloud.io/crowdsec/crowdsec/debian
        suites: "{{ ansible_facts['distribution_release'] }}"
        components: main
        signed_by: /etc/apt/keyrings/crowdsec.asc
        state: present

    - name: Install CrowdSec Security Engine (IDS)
      ansible.builtin.apt:
        name: crowdsec
        state: present
        update_cache: yes

    - name: Install CrowdSec Firewall Bouncer (IPS)
      ansible.builtin.apt:
        name: crowdsec-firewall-bouncer-iptables
        state: present

    - name: Ensure CrowdSec service is enabled and running
      ansible.builtin.systemd:
        name: crowdsec
        enabled: yes
        state: started

    - name: Ensure Firewall Bouncer service is enabled and running
      ansible.builtin.systemd:
        name: crowdsec-firewall-bouncer
        enabled: yes
        state: started
""",

    "docker.yml": """---
- name: Deploy Docker Container Engine
  hosts: edge_nodes
  gather_facts: true
  vars:
    admin_user: ansible_admin

  tasks:
    - name: Install system dependencies for secure apt communication
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
        state: present

    - name: Create secure directory for apt keyrings
      file:
        path: /etc/apt/keyrings
        state: directory
        mode: '0755'

    - name: Retrieve official Docker GPG signing key
      get_url:
        url: https://download.docker.com/linux/debian/gpg
        dest: /etc/apt/keyrings/docker.asc
        mode: '0644'

    - name: Register stable Docker upstream repository (deb822 format)
      ansible.builtin.deb822_repository:
        name: docker
        types: deb
        uris: https://download.docker.com/linux/debian
        suites: "{{ ansible_facts['distribution_release'] }}"
        components: stable
        signed_by: /etc/apt/keyrings/docker.asc
        state: present

    - name: Install Docker Engine and core plugins
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-buildx-plugin
          - docker-compose-plugin
        state: present
        update_cache: yes

    - name: Enforce Docker daemon active state
      ansible.builtin.service:
        name: docker
        state: started
        enabled: yes

    - name: Bind administrative user to docker group
      user:
        name: "{{ admin_user }}"
        groups: docker
        append: yes
      register: docker_group_bind

    - name: Force immediate SSH session reset to apply group permissions
      meta: reset_connection
      when: docker_group_bind.changed
""",

    "omada.yml": """---
- name: Deploy TP-Link Omada Controller in Docker
  hosts: edge_nodes
  gather_facts: false
  vars:
    omada_data_dir: /opt/omada
    omada_ver: "5.15"

  tasks:
    - name: Ensure target application directories exist with correct container permissions
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        mode: '0755'
        owner: "508"
        group: "508"
      loop:
        - "{{ omada_data_dir }}/data"
        - "{{ omada_data_dir }}/logs"

    - name: Start Omada Controller Container
      community.docker.docker_container:
        name: omada-controller
        image: "mbentley/omada-controller:{{ omada_ver }}"
        state: started
        restart_policy: unless-stopped
        network_mode: host
        env:
          TZ: "Europe/Berlin"
          MANAGE_HTTP_PORT: "8088"
          MANAGE_HTTPS_PORT: "8043"
        volumes:
          - "{{ omada_data_dir }}/data:/opt/tplink/EAPController/data"
          - "{{ omada_data_dir }}/logs:/opt/tplink/EAPController/logs"
"""
}

# 3. Definition der Obsidian-Dokumentation (.md)
OBSIDIAN_FILES = {
    "00_Overview/README.md": """# 🗺️ Distributed Edge Hub - Architecture & Dashboard

## Overview
This Obsidian vault contains the complete step-by-step technical blueprints, operational workflows, and active codebases for the "Schaufenster Integration Platform".

Our design decouples the **Control Plane** (centralized on a high-availability Cloud VPS in Germany) from the **Data Plane** (regional nodes running at local sites in Germany and Kenya). This ensures that even during regional network dropouts or localized power grid outages (e.g., in Kenya), your overall system control, local service routing, and core business monitoring dashboards remain fully functional.

---

## 📂 Active Vault Structure
To easily navigate or recreate this architecture from scratch, the files are modularized:

* **00_Overview / 02_System_Architecture_Blueprint.md**
    * The hybrid GitOps and Edge strategy combining cloud-routing with local Proxmox Kubernetes nodes.
* **01_Network / 01_Domain_and_Edge_Network.md**
    * Manual steps to buy, delegate, and configure DNS routing via IONOS and Cloudflare.
* **02_Provisioning / 02_Terraform_IaC.md**
    * Infrastructure-as-Code files and concrete terminal commands to spin up the Hetzner compute nodes.
* **03_Hardening / 03_Ansible_Configuration.md**
    * Step-by-step host preparation, local key agent provisioning, and automated hardening playbooks.
* **03_Hardening / 04_Docker_Installation.md**
    * Idempotent automated installation of the Docker Container Engine, GPG security keyrings, and Compose plugins.
* **03_Hardening / 05_Omada_Controller_Installation.md**
    * Automated deployment of the containerized TP-Link Omada SDN controller.
* **03_Hardening / 06_WireGuard_VPN_Hub_Installation.md**
    * Secure Site-to-Site WireGuard configuration interconnecting Germany, Kenya, and Admin clients.
* **03_Hardening / 07_IDS_IPS_CrowdSec_Installation.md**
    * Security engine (IDS) and firewall integration (IPS) via CrowdSec.
* **03_Hardening / 08_Security_Audit_Coexistence.md**
    * Deep-dive audit into Fail2ban/CrowdSec coexistence and OS-level kernel sysctl hardening.
* **03_Hardening / 09_Nginx_Reverse_Proxy_Setup.md**
    * Setting up Nginx, automating Let's Encrypt Wildcard SSL via Cloudflare DNS-01, and configuring the CrowdSec Nginx Web Bouncer.
* **03_Hardening / 10_Secret_Management_Strategies.md**
    * In-depth evaluation of GitOps secret isolation strategies.
* **04_Runbooks / 05_Verification_and_DR.md**
    * Operational sanity testing and the "3-Minute Complete Rebuild Loop" (Disaster Recovery).
""",

    "00_Overview/02_System_Architecture_Blueprint.md": """# 🗺️ Hybrid Cloud & Edge GitOps Architecture
> **The Big Picture: Decoupled Control, Private Data Sovereignty & Edge Autonomy**

This blueprint defines the final target state of our distributed infrastructure. It details the separation between our **Cloud Gateway Plane** (Hetzner VPS), our **Cloud Control Plane** (Management), and our **Local Edge Planes** (Germany & Kenya) running Kubernetes on Proxmox.

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
        │       Germany Local Node (Eichstätt)      │                                   │        Kenya Local Node (Kikambala)        │
        │       Subnet: 192.168.10.0/24             │                                   │       Subnet: 192.168.20.0/24             │
        ├───────────────────────────────────────────┤                                   ├───────────────────────────────────────────┤
        │  [Physical Proxmox VE Cluster]            │                                   │  [Physical Proxmox VE Edge Node]          │
        │    ┌─────────────────────────────────┐    │                                   │    ┌─────────────────────────────────┐    │
        │    │  Kubernetes (K8s) Cluster       │    │                                   │    │  Kubernetes (K8s) Cluster       │    │
        │    │  (Deployments managed via Git)  │    │                                   │    │  (Deployments managed via Git)  │    │
        │    ├─────────────────────────────────┤    │                                   │    ├─────────────────────────────────┤    │
        │    │  - Mailcow Backend (Mailboxes)  │    │                                   │    │  - Home Assistant KE (Local HA) │    │
        │    │  - Nextcloud Core & Databases   │    │                                   │    │  - Local MQTT & Node-RED        │    │
        │    │  - Home Assistant DE (Local HA) │    │                                   │    │  - Frigate NVR (AI Object Det.) │    │
        │    │  - GitLab / Gitea Runner        │    │                                   │    │  - Local Caching & Sync Agent   │    │
        │    └─────────────────────────────────┘    │                                   │    └─────────────────────────────────┘    │
        └───────────────────────────────────────────┘                                   └───────────────────────────────────────────┘
```

---

## ✉️ 1. The Secure Mail Architecture (Cloud SMTP-Relay ➔ Local Mailbox)
Operating a mail server directly from a home connection (DSL/Fiber) fails due to dynamic IPs, lack of PTR (Reverse DNS) configuration, and IP blocks on global spam lists (PBL). However, hosting your mailboxes in the cloud compromises data privacy. 

We solve this using a **Split SMTP Architecture**:

### Inbound E-Mail Flow:
1. An external server sends an email to \`user@knoer.net\`.
2. The DNS MX-record routing points to **VPS 2 (Cloud Control & Mail Relay)**.
3. The Cloud Relay receives the email on Port \`25\` (secured with TLS/DKIM checks).
4. The VPS immediately forwards the email **through the secure WireGuard tunnel** to the local **Mailcow Instance** running inside your **Kubernetes Cluster in Germany** (\`10.8.0.2\` or internal routed IP).
5. The mail is stored on your own physical disks in Eichstätt.
""",

    "01_Network/01_Domain_and_Edge_Network.md": """# 🌐 Network Setup: Domain Registration & Cloudflare Delegation

This cookbook details how to secure your domain namespace and delegate control to Cloudflare to establish rapid-propagation Anycast DNS.

---

## 🛠️ Step 1: Registrar Delegation (IONOS)
1. Log in to the **IONOS Control Center** (\`https://login.ionos.de\`).
2. Navigate to **Domains & SSL** and select your primary domain: \`knoer.net\`.
3. Click the **Nameservers** tab.
4. Select **Use custom nameservers** (Eigene Nameserver verwenden).
5. Input the following two authoritative Anycast servers provided by Cloudflare:
    * \`ashley.ns.cloudflare.com\`
    * \`will.ns.cloudflare.com\`
6. Click **Save** to delegate control.

---

## 🛠️ Step 2: Cloudflare Zone Setup
1. Log in to your **Cloudflare Dashboard** (\`https://dash.cloudflare.com\`).
2. Click **Add a Site** and input: \`knoer.net\`.
3. Select the **Free Plan** (fully adequate for production routing and SSL management).
4. Once the nameserver change is verified by Cloudflare, your status will turn to **Active**.
""",

    "02_Provisioning/02_Terraform_IaC.md": """# 🏗️ IaC Setup: Terraform Hetzner Cloud Provisioning

Follow these steps to establish a clean, repeatable infrastructure directory layout and spin up your cloud nodes in Germany.

---

## 📁 1. Local Directory Structure
On your MacBook, create the following directory framework:

```bash
mkdir -p ~/src/schaufenster/terraform/hcloud_vps
cd ~/src/schaufenster/terraform/hcloud_vps
```

---

## 📝 2. Create the Configuration Files

### File: \`main.tf\`
```hcl
provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_ssh_key" "admin_key" {
  name       = "macbook-ed25519"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "hcloud_server" "vps_edge" {
  name        = "edge-hub-vps"
  image       = "debian-12"
  server_type = "cx23"       # 2 vCPU, 4GB RAM, 40GB SSD
  location    = "fsn1"       # Falkenstein Data Center (Germany)
  ssh_keys    = [hcloud_ssh_key.admin_key.id]
}

resource "hcloud_firewall" "edge_firewall" {
  name = "edge-hub-firewall"

  # Secure Custom SSH Port Rule
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "2222"
    source_ips = ["0.0.0.0/0"]
  }

  # Allow standard SSH during initial provisioning (Delete this block after port migration!)
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0"]
  }

  apply_to {
    server = hcloud_server.vps_edge.id
  }
}

output "vps_ip" {
  value       = hcloud_server.vps_edge.ipv4_address
  description = "The public IPv4 address of the Edge VPS."
}
```
""",

    "03_Hardening/03_Ansible_Configuration.md": """# 🛠️ Ansible Configuration, SSH Agent Handling & Hardening

This playbook configures user access limits, updates security packages, moves your SSH port to \`2222\`, installs UFW, establishes a default-deny firewall policy, and resolves common Debian 12 Fail2ban-Systemd bugs.

---

## 🔒 Step 1: Secure Local SSH-Agent Handling on macOS
1. **Modify your local SSH client config** on your MacBook:
    ```text
    Host *
      AddKeysToAgent yes
      UseKeychain yes
      IdentityFile ~/.ssh/id_ed25519
    ```
2. **Spawn the SSH agent daemon** and feed your key once:
    ```bash
    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/id_ed25519
    ```

---

## 📝 Step 2: The Complete Hardening Playbook (\`site.yml\`)
```yaml
---
- name: Production Edge Node Hardening
  hosts: edge_nodes
  gather_facts: true
  become: true
  vars:
    custom_ssh_port: 2222
    admin_user: ansible_admin

  tasks:
    - name: Run safe APT upgrade cycle
      apt:
        update_cache: yes
        upgrade: safe
        cache_valid_time: 3600

    - name: Install baseline dependencies and security tools
      apt:
        name:
          - ufw
          - fail2ban
          - unattended-upgrades
          - curl
          - git
        state: present

    - name: Create non-root system administrative user
      user:
        name: "{{ admin_user }}"
        shell: /bin/bash
        groups: sudo
        append: yes
        state: present

    - name: Deploy authorized deployment public key
      authorized_key:
        user: "{{ admin_user }}"
        state: present
        key: "{{ lookup('file', '~/.ssh/id_ed25519.pub') }}"

    - name: Establish passwordless sudo escalation (Sudoers Isolation)
      copy:
        content: "{{ admin_user }} ALL=(ALL) NOPASSWD:ALL"
        dest: "/etc/sudoers.d/{{ admin_user }}"
        mode: '0440'
        validate: '/usr/sbin/visudo -cf %s'

    - name: Modify SSH Daemon configuration (Lockdown Directives)
      lineinfile:
        path: /etc/ssh/sshd_config
        regexp: "{{ item.regexp }}"
        line: "{{ item.line }}"
        state: present
      loop:
        - { regexp: '^#?Port ', line: 'Port {{ custom_ssh_port }}' }
        - { regexp: '^#?PermitRootLogin ', line: 'PermitRootLogin no' }
        - { regexp: '^#?PasswordAuthentication ', line: 'PasswordAuthentication no' }
        - { regexp: '^#?PubkeyAuthentication ', line: 'PubkeyAuthentication yes' }
      notify: Trigger SSHD Reboot

    - name: Allow custom SSH port in local UFW firewall
      community.general.ufw:
        rule: allow
        port: "{{ custom_ssh_port | string }}"
        proto: tcp

    - name: Set UFW default security policies (Zero-Trust)
      community.general.ufw:
        direction: "{{ item.direction }}"
        policy: "{{ item.policy }}"
      loop:
        - { direction: incoming, policy: deny }
        - { direction: outgoing, policy: allow }

    - name: Enforce and enable UFW Firewall state
      community.general.ufw:
        state: enabled

    - name: Enable automatic unattended updates
      copy:
        src: /usr/share/unattended-upgrades/20auto-upgrades
        dest: /etc/apt/apt.conf.d/20auto-upgrades
        remote_src: yes

    - name: Ensure fail2ban is enabled at boot
      systemd:
        name: fail2ban
        enabled: yes

    - name: Ensure fail2ban is running (Enforcing Idempotency)
      ansible.builtin.service:
        name: fail2ban
        state: started
      changed_when: false

  handlers:
    - name: Trigger SSHD Reboot
      systemd:
        name: sshd
        state: restarted
```
""",

    "03_Hardening/04_Docker_Installation.md": """# 🐳 Docker Installation & System Integration

This cookbook details how to deploy the Docker Container Engine and Compose plugins onto the hardened Debian 12 node using a completely idempotent Ansible playbook.

---

## 📝 Step 1: Create the Playbook (\`docker.yml\`)
```yaml
---
- name: Deploy Docker Container Engine
  hosts: edge_nodes
  gather_facts: true
  vars:
    admin_user: ansible_admin

  tasks:
    - name: Install system dependencies for secure apt communication
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
        state: present

    - name: Create secure directory for apt keyrings
      file:
        path: /etc/apt/keyrings
        state: directory
        mode: '0755'

    - name: Retrieve official Docker GPG signing key
      get_url:
        url: [https://download.docker.com/linux/debian/gpg](https://download.docker.com/linux/debian/gpg)
        dest: /etc/apt/keyrings/docker.asc
        mode: '0644'

    - name: Register stable Docker upstream repository (deb822 format)
      ansible.builtin.deb822_repository:
        name: docker
        types: deb
        uris: [https://download.docker.com/linux/debian](https://download.docker.com/linux/debian)
        suites: "{{ ansible_facts['distribution_release'] }}"
        components: stable
        signed_by: /etc/apt/keyrings/docker.asc
        state: present

    - name: Install Docker Engine and core plugins
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-buildx-plugin
          - docker-compose-plugin
        state: present
        update_cache: yes

    - name: Enforce Docker daemon active state
      ansible.builtin.service:
        name: docker
        state: started
        enabled: yes

    - name: Bind administrative user to docker group
      user:
        name: "{{ admin_user }}"
        groups: docker
        append: yes
      register: docker_group_bind

    - name: Force immediate SSH session reset to apply group permissions
      meta: reset_connection
      when: docker_group_bind.changed
```
""",

    "03_Hardening/05_Omada_Controller_Installation.md": """# 📡 TP-Link Omada Controller Deployment

This cookbook outlines the production-grade deployment of the TP-Link Omada Software Controller inside an isolated Docker container on our hardened Debian 12 Falkenstein VPS.

---

## 📝 Step 1: Ansible Playbook Setup (\`omada.yml\`)
```yaml
---
- name: Deploy TP-Link Omada Controller in Docker
  hosts: edge_nodes
  gather_facts: false
  vars:
    omada_data_dir: /opt/omada
    omada_ver: "5.15"

  tasks:
    - name: Ensure target application directories exist with correct container permissions
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        mode: '0755'
        owner: "508"
        group: "508"
      loop:
        - "{{ omada_data_dir }}/data"
        - "{{ omada_data_dir }}/logs"

    - name: Start Omada Controller Container
      community.docker.docker_container:
        name: omada-controller
        image: "mbentley/omada-controller:{{ omada_ver }}"
        state: started
        restart_policy: unless-stopped
        network_mode: host
        env:
          TZ: "Europe/Berlin"
          MANAGE_HTTP_PORT: "8088"
          MANAGE_HTTPS_PORT: "8043"
        volumes:
          - "{{ omada_data_dir }}/data:/opt/tplink/EAPController/data"
          - "{{ omada_data_dir }}/logs:/opt/tplink/EAPController/logs"
```
""",

    "03_Hardening/06_WireGuard_VPN_Hub_Installation.md": """# 🛡️ WireGuard VPN Hub Configuration (Site-to-Site & Omada Gateways)

This cookbook details the deployment of a centralized WireGuard VPN Hub on our hardened Hetzner VPS. This hub acts as the secure transit gateway, interconnecting our cloud services, local German infrastructure, Kenyan edge nodes, and administrative clients into a single encrypted private network (\`10.8.0.0/24\`).

---

## 📝 Step 1: Ansible Playbook Setup (\`wireguard.yml\`)
```yaml
---
- name: Install and configure WireGuard VPN Hub
  hosts: edge_nodes
  gather_facts: true
  become: true
  vars:
    vpn_network: "10.8.0.0/24"
    vpn_port: 51820
    server_ip: "10.8.0.1/24"
    germany_01_ip: "10.8.0.2/32"
    kenya_01_ip: "10.8.0.3/32"
    admin_01_ip: "10.8.0.4/32"
    germany_01_lan: "192.168.10.0/24"
    kenya_01_lan: "192.168.20.0/24"

  tasks:
    - name: Install WireGuard and routing tools
      ansible.builtin.apt:
        name:
          - wireguard
          - iptables
          - resolvconf
        state: present
        update_cache: yes

    - name: Create WireGuard directory with secure permissions
      ansible.builtin.file:
        path: /etc/wireguard
        state: directory
        mode: '0700'
        owner: root
        group: root

    # --- KEY GENERATION (Idempotent) ---

    - name: Check if server keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/server.key
      register: server_key_state

    - name: Generate server key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
      when: not server_key_state.stat.exists
      changed_when: true

    - name: Check if Germany 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/germany_01.key
      register: germany_01_key_state

    - name: Generate Germany 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/germany_01.key | wg pubkey > /etc/wireguard/germany_01.pub
      when: not germany_01_key_state.stat.exists
      changed_when: true

    - name: Check if Kenya 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/kenya_01.key
      register: kenya_01_key_state

    - name: Generate Kenya 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/kenya_01.key | wg pubkey > /etc/wireguard/kenya_01.pub
      when: not kenya_01_key_state.stat.exists
      changed_when: true

    - name: Check if Admin 01 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/admin_01.key
      register: admin_01_key_state

    - name: Generate Admin 01 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/admin_01.key | wg pubkey > /etc/wireguard/admin_01.pub
      when: not admin_01_key_state.stat.exists
      changed_when: true

    # --- READ KEYS ---

    - name: Slurp keys into Ansible variables
      ansible.builtin.slurp:
        src: "/etc/wireguard/{{ item }}"
      register: wg_keys
      loop:
        - server.key
        - server.pub
        - germany_01.key
        - germany_01.pub
        - kenya_01.key
        - kenya_01.pub
        - admin_01.key
        - admin_01.pub

    - name: Assign key variables
      ansible.builtin.set_fact:
        server_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.key') | first).content | b64decode | trim }}"
        server_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.pub') | first).content | b64decode | trim }}"
        germany_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'germany_01.key') | first).content | b64decode | trim }}"
        germany_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'germany_01.pub') | first).content | b64decode | trim }}"
        kenya_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'kenya_01.key') | first).content | b64decode | trim }}"
        kenya_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'kenya_01.pub') | first).content | b64decode | trim }}"
        admin_01_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'admin_01.key') | first).content | b64decode | trim }}"
        admin_01_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'admin_01.pub') | first).content | b64decode | trim }}"

    # --- NETWORK & ROUTING CONFIGURATION ---

    - name: Enable IPv4 packet forwarding in kernel (Sysctl)
      ansible.posix.sysctl:
        name: net.ipv4.ip_forward
        value: '1'
        sysctl_set: yes
        state: present
        reload: yes

    - name: Write WireGuard server configuration (wg0.conf)
      ansible.copy:
        dest: /etc/wireguard/wg0.conf
        owner: root
        group: root
        mode: '0600'
        content: |
          [Interface]
          Address = {{ server_ip }}
          ListenPort = {{ vpn_port }}
          PrivateKey = {{ server_private_key }}
          PostUp = ufw route allow in on wg0 out on eth0
          PostUp = ufw route allow in on wg0 out on wg0
          PostUp = iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
          PostDown = ufw route delete allow in on wg0 out on eth0
          PostDown = ufw route delete allow in on wg0 out on wg0
          PostDown = iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

          [Peer]
          PublicKey = {{ germany_01_public_key }}
          AllowedIPs = {{ germany_01_ip }}, {{ germany_01_lan }}

          [Peer]
          PublicKey = {{ kenya_01_public_key }}
          AllowedIPs = {{ kenya_01_ip }}, {{ kenya_01_lan }}

          [Peer]
          PublicKey = {{ admin_01_public_key }}
          AllowedIPs = {{ admin_01_ip }}
      notify: Restart WireGuard

    # --- GENERATE CLIENT CONFIGURATIONS ---

    - name: Create directory for client configurations
      ansible.builtin.file:
        path: /etc/wireguard/clients
        state: directory
        mode: '0700'
        owner: root
        group: root

    - name: Generate Germany 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-germany-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ germany_01_private_key }}
          Address = 10.8.0.2/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ kenya_01_lan }}
          PersistentKeepalive = 25

    - name: Generate Kenya 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-kenya-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ kenya_01_private_key }}
          Address = 10.8.0.3/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ germany_01_lan }}
          PersistentKeepalive = 25

    - name: Generate Admin 01 client configuration
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-admin-01.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ admin_01_private_key }}
          Address = 10.8.0.4/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.knoer.net:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ germany_01_lan }}, {{ kenya_01_lan }}
          PersistentKeepalive = 25

    # --- SERVICE START ---

    - name: Allow WireGuard port in local UFW firewall
      community.general.ufw:
        rule: allow
        port: "{{ vpn_port | string }}"
        proto: udp

    - name: Enable and start WireGuard Systemd service
      ansible.builtin.systemd:
        name: wg-quick@wg0
        enabled: yes
        state: started

  handlers:
    - name: Restart WireGuard
      ansible.builtin.systemd:
        name: wg-quick@wg0
        state: restarted
""",

    "crowdsec.yml": """---
- name: Install and configure CrowdSec IDS/IPS
  hosts: edge_nodes
  gather_facts: true
  become: true

  tasks:
    - name: Ensure prerequisites are installed
      ansible.builtin.apt:
        name:
          - curl
          - gnupg
          - apt-transport-https
        state: present
        update_cache: yes

    - name: Create secure directory for apt keyrings
      ansible.builtin.file:
        path: /etc/apt/keyrings
        state: directory
        mode: '0755'

    - name: Retrieve official CrowdSec GPG signing key
      ansible.builtin.get_url:
        url: [https://packagecloud.io/crowdsec/crowdsec/gpgkey](https://packagecloud.io/crowdsec/crowdsec/gpgkey)
        dest: /etc/apt/keyrings/crowdsec.asc
        mode: '0644'

    - name: Register CrowdSec stable repository (deb822 format)
      ansible.builtin.deb822_repository:
        name: crowdsec
        types: deb
        uris: [https://packagecloud.io/crowdsec/crowdsec/debian](https://packagecloud.io/crowdsec/crowdsec/debian)
        suites: "{{ ansible_facts['distribution_release'] }}"
        components: main
        signed_by: /etc/apt/keyrings/crowdsec.asc
        state: present

    - name: Install CrowdSec Security Engine (IDS)
      ansible.builtin.apt:
        name: crowdsec
        state: present
        update_cache: yes

    - name: Install CrowdSec Firewall Bouncer (IPS)
      ansible.builtin.apt:
        name: crowdsec-firewall-bouncer-iptables
        state: present

    - name: Ensure CrowdSec service is enabled and running
      ansible.builtin.systemd:
        name: crowdsec
        enabled: yes
        state: started

    - name: Ensure Firewall Bouncer service is enabled and running
      ansible.builtin.systemd:
        name: crowdsec-firewall-bouncer
        enabled: yes
        state: started
"""
}

# 3. Schreiben der Ansible-Dateien auf die Festplatte
print(f"[*] Starte Generierung der Ansible-Dateien in: {ANSIBLE_DIR}")
for filename, content in ANSIBLE_FILES.items():
    filepath = os.path.join(ANSIBLE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Ansible-Datei erstellt: {filepath}")

# 4. Automatisches Erstellen der unversionierten .gitignore im Ansible-Verzeichnis
gitignore_path = os.path.join(ANSIBLE_DIR, ".gitignore")
if not os.path.exists(gitignore_path):
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("*.asvars\n")
    print(f"[+] .gitignore erfolgreich erstellt: {gitignore_path}")

# 5. Schreiben der Obsidian-Dokumentation (.md)
print(f"[*] Starte Generierung der Obsidian-Dateien in: {OBSIDIAN_DIR}")
for relative_path, content in OBSIDIAN_FILES.items():
    full_path = os.path.join(OBSIDIAN_DIR, relative_path)
    # Erstelle die Unterordner (z.B. 00_Overview, 03_Hardening) falls nicht vorhanden
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Obsidian-Handbuch erstellt: {full_path}")

print("\\n[*] BOOTSTRAP ERFOLGREICH ABGESCHLOSSEN!")
print(f"[-] Ansible-Playbooks liegen unter:  {ANSIBLE_DIR}")
print(f"[-] Obsidian-Handbuecher liegen unter: {OBSIDIAN_DIR}")
print("[!] Du kannst den Inhalt von 'obsidian_vault' jetzt direkt in deinen Obsidian-Ordner ziehen.")