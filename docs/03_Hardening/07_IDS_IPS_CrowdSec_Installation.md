# 🛡️ IDS/IPS Integration via CrowdSec

To protect our hardened Cloud VPS from brute-force attempts, port scans, and application-layer exploits, we deploy **CrowdSec**.

---

## 📝 Step 1: Ansible Playbook Setup (`crowdsec.yml`)
```yaml
---
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
```

---

## 🚀 Step 2: Deployment
```bash
ansible-playbook -i inventory.ini crowdsec.yml
```