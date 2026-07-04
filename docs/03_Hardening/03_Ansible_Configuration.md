# 🛠️ Ansible Configuration, SSH Agent Handling & Hardening

This playbook configures user access limits, updates security packages, moves your SSH port to `2222`, installs UFW, establishes a default-deny firewall policy, and resolves common Debian 12 Fail2ban-Systemd bugs.

---

## 🔒 Step 1: Secure Local SSH-Agent Handling on macOS
1.  **Modify your local SSH client config** on your MacBook:
    ```text
    Host *
      AddKeysToAgent yes
      UseKeychain yes
      IdentityFile ~/.ssh/id_ed25519
    ```
2.  **Spawn the SSH agent daemon** and feed your key once:
    ```bash
    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/id_ed25519
    ```

---

## 📝 Step 2: The Complete Hardening Playbook (`site.yml`)
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

---

## 🚀 Step 3: Deployment Runbook
```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory.ini site.yml
```