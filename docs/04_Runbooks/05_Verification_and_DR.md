# 🏁 Security Verification & 3-Minute Disaster Recovery (DR)

Keep this runbook handy for auditing security controls and rebuilding your compute infrastructure quickly in case of node failure.

---

## 🛡️ Part 1: Security Audit Routines
Run these checks from your local MacBook to verify your hardening rules are working.

### Check 1: Blocked Root Login & Port 22 (Expect: Refused or Timeout)
```bash
ssh -p 22 root@edge.yourdomain.com
```

### Check 2: Blocked Password Logins (Expect: Pubkey Denied)
```bash
ssh -o PubkeyAuthentication=no -p 2222 ansible_admin@edge.yourdomain.com
```

---

## 🌪️ Part 2: The 3-Minute Disaster Recovery (DR) Rebuild

### Step 1: Force-Destroy and Redeploy Hardware Platforms
```bash
cd ~/src/schaufenster/terraform/hcloud_vps
terraform apply -replace="hcloud_server.vps_edge"
```

### Step 2: Run the Ansible Security Mesh
```bash
cd ~/src/schaufenster/ansible
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory.ini site.yml
ansible-playbook -i inventory.ini docker.yml
ansible-playbook -i inventory.ini wireguard.yml
ansible-playbook -i inventory.ini crowdsec.yml
ansible-playbook -i inventory.ini nginx_proxy.yml
```