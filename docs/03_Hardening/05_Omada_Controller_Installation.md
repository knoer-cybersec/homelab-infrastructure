# 📡 TP-Link Omada Controller Deployment

This cookbook outlines the production-grade deployment of the TP-Link Omada Software Controller inside an isolated Docker container on our hardened Debian 12 VPS.

---

## 📝 Step 1: Ansible Playbook Setup (`omada.yml`)
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

---

## 🚀 Step 2: Deployment Orchestration
```bash
ansible-playbook -i inventory.ini omada.yml
```