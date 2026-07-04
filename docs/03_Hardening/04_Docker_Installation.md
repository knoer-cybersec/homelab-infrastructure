# 🐳 Docker Installation & System Integration

This cookbook details how to deploy the Docker Container Engine and Compose plugins onto the hardened Debian 12 node using a completely idempotent Ansible playbook.

---

## 📝 Step 1: Create the Playbook (`docker.yml`)
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
```

---

## 🚀 Step 2: Running the Playbook
```bash
ansible-playbook -i inventory.ini docker.yml
```