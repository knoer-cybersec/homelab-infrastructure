# 🛡️ Security Audit & Ultimate Hardening Checklist

This audit evaluates the architectural relationship between Fail2ban and CrowdSec, assesses our current security posture, and outlines the final steps to achieve an enterprise-grade, ultimately hardened edge node.

---

## ⚔️ Part 1: CrowdSec vs. Fail2ban — Do They Clash?
The short answer is: **No, they do not clash technically, but having both run permanently is redundant.**

* **Fail2ban** creates its own target chains (prefixed with `f2b-`) in Netfilter/iptables.
* **CrowdSec** (via the firewall bouncer) creates a dedicated set of ipsets and rules under `crowdsec-chains`.

---

## 🚀 Part 2: The Last 5% — Achieving "Ultimate" Hardening

### Step 1: Close Port 8043 (Omada Controller UI) to the Public Internet
Now that your WireGuard Admin Tunnel is active, there is **zero reason** for Port `8043` to remain open on the public Cloud Firewall.
1.  Log into your **Cloud Console**.
2.  Go to your **Firewall Configuration**.
3.  **Delete the inbound rule allowing TCP Port 8043.**

### Step 2: OS Kernel Hardening via Sysctl
Add this task block to your overreaching **`site.yml`** playbook to automate kernel hardening:

```yaml
    - name: Configure hardened kernel parameters (Sysctl)
      ansible.posix.sysctl:
        name: "{{ item.key }}"
        value: "{{ item.value }}"
        sysctl_set: yes
        state: present
        reload: yes
      loop:
        # Prevent IP Spoofing (Reverse Path Filtering)
        - { key: 'net.ipv4.conf.all.rp_filter', value: '1' }
        - { key: 'net.ipv4.conf.default.rp_filter', value: '1' }
        # Do not accept ICMP redirects (prevents MITM route hijacking)
        - { key: 'net.ipv4.conf.all.accept_redirects', value: '0' }
        - { key: 'net.ipv6.conf.all.accept_redirects', value: '0' }
        - { key: 'net.ipv4.conf.all.send_redirects', value: '0' }
        # Protect against TCP SYN Flood attacks
        - { key: 'net.ipv4.tcp_syncookies', value: '1' }
        - { key: 'net.ipv4.tcp_max_syn_backlog', value: '2048' }
        - { key: 'net.ipv4.tcp_synack_retries', value: '2' }
        # Disable source routing (prevents packet routing exploitation)
        - { key: 'net.ipv4.conf.all.accept_source_route', value: '0' }
        - { key: 'net.ipv6.conf.all.accept_source_route', value: '0' }
```

### Step 3: Secure Shared Memory `/dev/shm`
```yaml
    - name: Harden /dev/shm mount options
      ansible.posix.mount:
        path: /dev/shm
        src: tmpfs
        fstype: tmpfs
        opts: defaults,noexec,nosuid,nodev
        state: remounted
```