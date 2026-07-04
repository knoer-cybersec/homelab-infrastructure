# 🌐 Nginx Reverse Proxy, Let's Encrypt Wildcard SSL & CrowdSec Layer-7 IPS
> **Establish VPS 1 as the Secure Wildcard SSL Entry Gateway and L7 Shield for Private Backends**

This cookbook details the deployment of a hardened Nginx Reverse Proxy on **VPS 1**. It acts as the TLS termination point, routing public web requests safely through the WireGuard VPN tunnel to private application nodes.

Instead of exposing individual services via separate public IP certificates, we deploy a **Let's Encrypt Wildcard SSL Certificate (`*.yourdomain.com` and `yourdomain.com`)** using the **Cloudflare DNS-01 Challenge**. This completely conceals our internal subdomain structure from public Certificate Transparency Logs and eliminates the need to renew individual certificates per service.

Additionally, we integrate the **CrowdSec Nginx Web Bouncer** to actively block application-layer threats directly at the HTTP layer.

To prevent secrets from leaking into public Git repositories, the Cloudflare API Token is dynamically loaded via a local environment variable during execution.

---

## 📝 Step 1: Self-Healing Ansible Playbook Setup (`nginx_proxy.yml`)

This playbook automates the installation of Nginx, Certbot with the Cloudflare DNS plugin, and the CrowdSec Nginx Bouncer. It incorporates a **robust, self-healing registration sequence** to automatically configure the bouncer's API credentials.

```yaml
---
- name: Deploy Nginx Reverse Proxy and Web Security
  hosts: edge_nodes
  gather_facts: true
  become: true
  vars:
    admin_user: ansible_admin
    # Load API token dynamically from local environment variables on your MacBook
    cloudflare_api_token: "{{ lookup('ansible.builtin.env', 'CLOUDFLARE_API_TOKEN') }}"

  tasks:
    - name: Verify Cloudflare API Token is set
      ansible.builtin.fail:
        msg: "FEHLER: Die lokale Umgebungsvariable 'CLOUDFLARE_API_TOKEN' ist nicht gesetzt!"
      when: cloudflare_api_token is undefined or cloudflare_api_token | length == 0
      delegate_to: localhost
      become: false

    - name: Install Nginx, Certbot and security dependencies
      ansible.builtin.apt:
        name:
          - nginx
          - certbot
          - python3-certbot-nginx
          - python3-certbot-dns-cloudflare
          - crowdsec-nginx-bouncer
        state: present
        update_cache: yes

    - name: Create secure Let's Encrypt configuration directory
      ansible.builtin.file:
        path: /etc/letsencrypt
        state: directory
        mode: '0700'
        owner: root
        group: root

    - name: Deploy Cloudflare API Credentials for DNS-01 Challenge
      ansible.builtin.copy:
        dest: /etc/letsencrypt/cloudflare.ini
        owner: root
        group: root
        mode: '0600'
        content: |
          # Cloudflare API token used by Certbot
          dns_cloudflare_api_token = "{{ cloudflare_api_token }}"

    - name: Register Web Bouncer in local CrowdSec Security Engine
      ansible.builtin.shell: |
        cscli bouncers add nginx-bouncer || true
      register: bouncer_register_output
      changed_when: "'Api key' in bouncer_register_output.stdout"

    - name: Extract and write CrowdSec API Key to Nginx Bouncer configuration
      ansible.builtin.shell: |
        KEY=$(echo "{{ bouncer_register_output.stdout }}" | grep -oP "API Key: \K\w+")
        if [ ! -z "$KEY" ]; then
          sed -i "s/API_KEY=.*/API_KEY=$KEY/" /etc/crowdsec/bouncers/crowdsec-nginx-bouncer.conf
        fi
      when: bouncer_register_output.changed

    - name: Ensure correct CrowdSec API endpoint in Nginx Bouncer configuration
      ansible.builtin.lineinfile:
        path: /etc/crowdsec/bouncers/crowdsec-nginx-bouncer.conf
        regexp: '^API_URL='
        line: 'API_URL=http://127.0.0.1:8080'
        state: present

    - name: Deploy hardened global SSL parameters
      ansible.builtin.copy:
        dest: /etc/nginx/conf.d/ssl-global.conf
        owner: root
        group: root
        mode: '0644'
        content: |
          # Modern, secure TLS baseline (Mozilla Modern Profile)
          ssl_protocols TLSv1.2 TLSv1.3;
          ssl_prefer_server_ciphers on;
          ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
          
          # Performance tunings for reverse proxy operations
          ssl_session_cache shared:SSL:10m;
          ssl_session_timeout 1d;
          ssl_session_tickets off;
          
          # HSTS (HTTP Strict Transport Security) - Force HTTPS for 1 Year
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
          
          # Defend against clickjacking & cross-site scripting (XSS)
          add_header X-Frame-Options DENY always;
          add_header X-Content-Type-Options nosniff always;
          add_header X-XSS-Protection "1; mode=block" always;
      notify: Reload Nginx

    - name: Open Web ports in local UFW firewall
      community.general.ufw:
        rule: allow
        port: "{{ item }}"
        proto: tcp
      loop:
        - "80"
        - "443"

    - name: Ensure Nginx is enabled at boot and active
      ansible.builtin.systemd:
        name: nginx
        enabled: yes
        state: started

  handlers:
    - name: Reload Nginx
      ansible.builtin.systemd:
        name: nginx
        state: reloaded
```

---

## 🚀 Step 2: Provisioning Let's Encrypt Wildcard Certificates

Log into **VPS 1** and trigger the automated DNS-01 challenge:

```bash
ssh -p 2222 ansible_admin@edge.yourdomain.com
sudo certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d yourdomain.com \
  -d "*.yourdomain.com" \
  --preferred-challenges dns-01
```
*This generates a secure wildcard certificate under `/etc/letsencrypt/live/yourdomain.com/`.*

---

## 📝 Step 3: Routing Config — Wildcard Virtual Host Routing

We configure Nginx to route subdomains safely over WireGuard backends.

### Configuration Block: `/etc/nginx/sites-available/yourdomain.com`
```nginx
# 1. Catch-all HTTP Port 80 and Redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.com *.yourdomain.com;
    return 301 https://$host$request_uri;
}

# 2. Omada SDN Controller (edge.yourdomain.com)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name edge.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass https://127.0.0.1:8043;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Websocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# 3. Nextcloud (Location 1 Local K8s - 10.8.0.2)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name cloud.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://10.8.0.2:80; # Sent inside safe encrypted WireGuard tunnel
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 4. Smart Home Location 2 (location-2-smart.yourdomain.com - 10.8.0.3)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name location-2-smart.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://10.8.0.3:80; # Sent inside safe encrypted WireGuard tunnel
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and test configuration:
```bash
sudo ln -s /etc/nginx/sites-available/yourdomain.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```
