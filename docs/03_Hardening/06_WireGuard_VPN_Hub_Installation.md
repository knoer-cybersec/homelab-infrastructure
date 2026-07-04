# 🛡️ WireGuard VPN Hub Configuration (Site-to-Site & Omada Gateways)

This cookbook details the deployment of a centralized WireGuard VPN Hub on our hardened Cloud VPS. This hub acts as the secure transit gateway, interconnecting our cloud services, local Location 1 infrastructure, Location 2 edge nodes, and administrative clients into a single encrypted private network (`10.8.0.0/24`).

---

## 📝 Step 1: Ansible Playbook Setup (`wireguard.yml`)
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
    
    # Client Tunnel IPs
    location_1_ip: "10.8.0.2/32"
    location_2_ip: "10.8.0.3/32"
    admin_01_ip: "10.8.0.4/32"

    # Local Physical LAN Subnets of your sites
    location_1_lan: "192.168.10.0/24"
    location_2_lan: "192.168.20.0/24"

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

    - name: Check if Location 1 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/location_1.key
      register: location_1_key_state

    - name: Generate Location 1 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/location_1.key | wg pubkey > /etc/wireguard/location_1.pub
      when: not location_1_key_state.stat.exists
      changed_when: true

    - name: Check if Location 2 keys already exist
      ansible.builtin.stat:
        path: /etc/wireguard/location_2.key
      register: location_2_key_state

    - name: Generate Location 2 key pair
      ansible.builtin.shell: |
        wg genkey | tee /etc/wireguard/location_2.key | wg pubkey > /etc/wireguard/location_2.pub
      when: not location_2_key_state.stat.exists
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
        - location_1.key
        - location_1.pub
        - location_2.key
        - location_2.pub
        - admin_01.key
        - admin_01.pub

    - name: Assign key variables
      ansible.builtin.set_fact:
        server_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.key') | first).content | b64decode | trim }}"
        server_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'server.pub') | first).content | b64decode | trim }}"
        location_1_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'location_1.key') | first).content | b64decode | trim }}"
        location_1_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'location_1.pub') | first).content | b64decode | trim }}"
        location_2_private_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'location_2.key') | first).content | b64decode | trim }}"
        location_2_public_key: "{{ (wg_keys.results | selectattr('item', 'equalto', 'location_2.pub') | first).content | b64decode | trim }}"
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

          # Client Peer 1: Location 1 Gateway
          [Peer]
          PublicKey = {{ location_1_public_key }}
          AllowedIPs = {{ location_1_ip }}, {{ location_1_lan }}

          # Client Peer 2: Location 2 Gateway
          [Peer]
          PublicKey = {{ location_2_public_key }}
          AllowedIPs = {{ location_2_ip }}, {{ location_2_lan }}

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

    - name: Generate Location 1 client configuration (wg0-location-1.conf)
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-location-1.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ location_1_private_key }}
          Address = 10.8.0.2/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.yourdomain.com:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ location_2_lan }}
          PersistentKeepalive = 25

    - name: Generate Location 2 client configuration (wg0-location-2.conf)
      ansible.copy:
        dest: /etc/wireguard/clients/wg0-location-2.conf
        mode: '0600'
        content: |
          [Interface]
          PrivateKey = {{ location_2_private_key }}
          Address = 10.8.0.3/24
          DNS = 1.1.1.1

          [Peer]
          PublicKey = {{ server_public_key }}
          Endpoint = edge.yourdomain.com:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ location_1_lan }}
          PersistentKeepalive = 25

    - name: Generate Admin 01 client configuration (wg0-admin-01.conf)
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
          Endpoint = edge.yourdomain.com:{{ vpn_port }}
          AllowedIPs = {{ vpn_network }}, {{ location_1_lan }}, {{ location_2_lan }}
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
```

---

## 🚀 Step 2: Deployment Orchestration
```bash
ansible-playbook -i inventory.ini wireguard.yml
```