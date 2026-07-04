# 🏗️ IaC Setup: Terraform Cloud Provisioning

Follow these steps to establish a clean, repeatable infrastructure directory layout and spin up your cloud nodes.

---

## 📁 1. Local Directory Structure
On your MacBook, create the following directory framework:

```bash
mkdir -p ~/src/schaufenster/terraform/hcloud_vps
cd ~/src/schaufenster/terraform/hcloud_vps
```

---

## 📝 2. Create the Configuration Files

### File: `main.tf`
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
  location    = "fsn1"       # Falkenstein Data Center
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

---

## 🚀 3. Execution Runbook
```bash
terraform init
terraform plan
terraform apply
```