# ==============================================================================
# Input Variables for Multi-Cloud Infrastructure (Hetzner & Cloudflare)
# ==============================================================================

variable "hcloud_token" {
  type        = string
  description = "Secret API Token for Hetzner Cloud"
  sensitive   = true
}

variable "cloudflare_token" {
  type        = string
  description = "Secret API Token generated within Cloudflare Dashboard"
  sensitive   = true
}

variable "cloudflare_zone_id" {
  type        = string
  description = "The unique Target Zone ID for the domain hosted within Cloudflare"
}

variable "domain_name" {
  type        = string
  description = "The primary root domain name (e.g., domain.com)"
}

variable "ssh_public_key" {
  type        = string
  description = "Authorized public SSH key for infrastructure root authorization"
}