# 🗺️ Distributed Edge Hub - Architecture & Dashboard

## Overview
This Obsidian vault contains the complete step-by-step technical blueprints, operational workflows, and active codebases for the "Schaufenster Integration Platform".

Our design decouples the **Control Plane** (centralized on a high-availability Cloud VPS) from the **Data Plane** (regional nodes running at local sites named Location 1 and Location 2). This ensures that even during regional network dropouts or localized power grid outages, your overall system control, local service routing, and core business monitoring dashboards remain fully functional.

---

## 📂 Active Vault Structure
To easily navigate or recreate this architecture from scratch, the files are modularized:

* **00_Overview / [02_System_Architecture_Blueprint.md]**
    * The hybrid GitOps and Edge strategy combining cloud-routing with local Proxmox Kubernetes nodes.
* **01_Network / [01_Domain_and_Edge_Network.md]**
    * Steps to buy, delegate, and configure DNS routing via your registrar and Cloudflare.
* **02_Provisioning / [02_Terraform_IaC.md]**
    * Infrastructure-as-Code files and concrete terminal commands to spin up the Cloud compute nodes.
* **03_Hardening / [03_Ansible_Configuration.md]**
    * Step-by-step host preparation, local key agent provisioning, and automated hardening playbooks.
* **03_Hardening / [04_Docker_Installation.md]**
    * Idempotent automated installation of the Docker Container Engine, GPG security keyrings, and Compose plugins.
* **03_Hardening / [05_Omada_Controller_Installation.md]**
    * Automated deployment of the containerized TP-Link Omada SDN controller.
* **03_Hardening / [06_WireGuard_VPN_Hub_Installation.md]**
    * Secure Site-to-Site WireGuard configuration interconnecting Location 1, Location 2, and Admin clients.
* **03_Hardening / [07_IDS_IPS_CrowdSec_Installation.md]**
    * Security engine (IDS) and firewall integration (IPS) via CrowdSec.
* **03_Hardening / [08_Security_Audit_Coexistence.md]**
    * Deep-dive audit into Fail2ban/CrowdSec coexistence and OS-level kernel sysctl hardening.
* **03_Hardening / [09_Nginx_Reverse_Proxy_Setup.md]**
    * Setting up Nginx, automating Let's Encrypt Wildcard SSL via Cloudflare DNS-01, and configuring the CrowdSec Nginx Web Bouncer.
* **03_Hardening / [10_Secret_Management_Strategies.md]**
    * In-depth evaluation of GitOps secret isolation strategies.
* **04_Runbooks / [05_Verification_and_DR.md]**
    * Operational sanity testing and the "3-Minute Complete Rebuild Loop" (Disaster Recovery).