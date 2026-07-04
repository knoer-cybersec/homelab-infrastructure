# ==============================================================================
# Multi-Cloud Deployment: Hetzner Compute Node & Cloudflare DNS Engineering
# ==============================================================================

# 1. Register Administrative SSH Key within Hetzner
resource "hcloud_ssh_key" "admin_key" {
  name       = "infrastructure-admin-key"
  public_key = var.ssh_public_key
}

# 2. Deploy Cloud Edge Compute Node (ARM64 Ampere Altra / CAX11)
resource "hcloud_server" "vps_edge" {
  name        = "edge-hub-vps"
  image       = "debian-12"
  server_type = "cx23"
  location    = "nbg1"
  ssh_keys    = [hcloud_ssh_key.admin_key.id]
}

# 3. Hetzner Stateful Network Firewall Layer
resource "hcloud_firewall" "edge_firewall" {
  name = "edge-bastion-firewall"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "2222"
    source_ips = ["0.0.0.0/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "25"
    source_ips = ["0.0.0.0/0"]
  }

  rule {
    direction  = "in"
    protocol   = "udp"
    port       = "51820"
    source_ips = ["0.0.0.0/0"]
  }

  apply_to {
    server = hcloud_server.vps_edge.id
  }
}

# 4. Cloudflare Orchestration: Edge Routing Records
resource "cloudflare_record" "vps_a_record" {
  zone_id = var.cloudflare_zone_id
  name    = "edge"
  type    = "A"
  content = hcloud_server.vps_edge.ipv4_address
  ttl     = 3600
  proxied = false 
}

# ==============================================================================
# TEMPORARILY DISABLED: Mail Infrastructure Records
# We will uncomment these once Phase 4 (Mailserver Setup) is ready to deploy.
# ==============================================================================
# resource "cloudflare_record" "mx_record" {
#   zone_id  = var.cloudflare_zone_id
#   name     = "@"
#   type     = "MX"
#   content  = "edge.${var.domain_name}"
#   priority = 10
#   ttl      = 3600
# }
#
# resource "cloudflare_record" "spf_record" {
#   zone_id = var.cloudflare_zone_id
#   name    = "@"
#   type    = "TXT"
#   content = "v=spf1 ip4:${hcloud_server.vps_edge.ipv4_address} -all"
#   ttl     = 3600
# }

# ==============================================================================
# Technical Infrastructure Outputs
# ==============================================================================
output "vps_public_ip" {
  value       = hcloud_server.vps_edge.ipv4_address
  description = "The public IPv4 address assigned by Hetzner to the Edge Node"
}