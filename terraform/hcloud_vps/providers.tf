# ==============================================================================
# Multi-Cloud Configuration (Hetzner Cloud Compute & Cloudflare Enterprise DNS)
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

# Cloudflare utilizes a clean, single API Token authentication layout
provider "cloudflare" {
  api_token = var.cloudflare_token
}