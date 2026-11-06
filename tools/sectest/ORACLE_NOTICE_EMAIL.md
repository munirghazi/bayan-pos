# Oracle security-testing notification (send 5 business days before testing)

**To:** security_test_notification_grp@oracle.com
**Subject:** Cloud Security Testing Notification — tenancy vits — penetration and vulnerability test of customer components

Fill in the bracketed items. Find your public IP on the laptop with `curl -s https://ifconfig.me`. Your IP is dynamic, so check it on the day; if it changes, list a range or send a short update.

---

Hello,

We are notifying Oracle, as required by the Oracle Cloud Security Testing Policy, of a penetration and vulnerability test of resources we have deployed in our own OCI tenancy. We will not test the underlying OCI services, the OCI console or the OCI APIs, and we will not perform any denial-of-service or load testing.

**Technical contact**
- Name: Munir Farajallah
- Email: [your work email]
- Phone number: [mobile]
- Backup phone number: [second number]

**Testing details**
- Start date: [date, at least 5 business days after sending]
- Duration (days): 3
- Purpose: security assessment of our own web application before onboarding more customers
- Description: authenticated and unauthenticated application testing (tenant isolation, authentication, authorisation, file upload validation, business-logic checks), TLS and HTTP-header review, and a TCP port scan of our single compute instance. Low request rates only. No denial-of-service, no load or stress testing, no attempts against OCI services.
- Source IP address or range: [your public IP]
- Services to be tested: OCI Compute instance (customer application only)
- Target tenancy name: vits
- Target region: me-jeddah-1
- Target IP addresses: 158.101.250.177 (hostnames sahlpos.roaa.sa, admin.sahlpos.roaa.sa)
- Tooling to be used: nmap (TCP connect scan), curl, openssl s_client, custom Python scripts (httpx) at low request rates

Regards,
Munir Farajallah
Ruya Solutions for Information Technology
