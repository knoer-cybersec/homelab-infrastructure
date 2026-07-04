# 🌐 Network Setup: Domain Registration & Cloudflare Delegation

This cookbook details how to secure your domain namespace and delegate control to Cloudflare to establish rapid-propagation Anycast DNS.

---

## 🛠️ Step 1: Registrar Delegation
1.  Log in to your Domain Registrar Control Center.
2.  Navigate to **Domains & SSL** and select your primary domain: `yourdomain.com`.
3.  Click the **Nameservers** tab.
4.  Select **Use custom nameservers**.
5.  Input the following two authoritative Anycast servers provided by Cloudflare:
    * `ashley.ns.cloudflare.com`
    * `will.ns.cloudflare.com`
6.  Click **Save** to delegate control.

---

## 🛠️ Step 2: Cloudflare Zone Setup
1.  Log in to your **Cloudflare Dashboard** (`https://dash.cloudflare.com`).
2.  Click **Add a Site** and input: `yourdomain.com`.
3.  Select the **Free Plan** (fully adequate for production routing and SSL management).
4.  Once the nameserver change is verified by Cloudflare, your status will turn to **Active**.

---

## 🛠️ Step 3: Configuring the Edge A-Record
To route traffic safely to your Cloud VPS, define a dedicated, unproxied subdomain record.

1.  In Cloudflare, go to **DNS ➔ Records**.
2.  Click **Add Record**.
3.  Input the following exact parameters:
    * **Type:** `A`
    * **Name:** `edge` (This creates the FQDN `edge.yourdomain.com`)
    * **IPv4 Address:** `[YOUR_CLOUD_VPS_IP]`
    * **Proxy Status:** Set to **DNS Only (Grey Cloud)**.
    * **TTL:** `Auto` (Default)
4.  Click **Save** to apply the record.