markdown
# Security Policy

## Introduction

We take the security of our project seriously. This policy outlines our process for handling security vulnerabilities in a responsible manner.

## Supported Versions

We provide security updates **only** for the latest major release. Older versions are considered end‑of‑life and will not receive patches.

| Version       | Supported          |
|---------------|--------------------|
| Latest major  | ✅ Active          |
| Previous      | ❌ End‑of‑life     |

## Reporting a Vulnerability

If you believe you have found a security vulnerability, please follow our **responsible disclosure** process.

### Guidelines

- **Do** submit your report privately using the methods below.
- **Do** provide sufficient detail to allow us to reproduce the issue.
- **Do** include a CVSS score (or estimate) and potential impact.
- **Do not** create a public issue, pull request, or forum post.
- **Do not** exploit the vulnerability beyond the minimal steps needed to demonstrate it.

### How to Report

1. **Email** our security team at **security@example.com**  
   If you use PGP encryption, please encrypt to the key at `https://example.com/security.asc`  
   (fingerprint: `ABCD 1234 5678 90EF ...`).

2. **Include** in your report:
   - Description of the vulnerability and its potential impact.
   - Steps to reproduce – minimal, clear, and reliable.
   - Affected version(s) or commit hashes.
   - Any existing mitigations or workarounds.
   - Your preferred contact for follow‑up (email preferred).

3. **Response** – We will acknowledge receipt within **48 hours** and provide an initial assessment timeline.

### What Happens Next

- We will work with you to **validate and reproduce** the issue.
- Once confirmed, we will develop a fix, coordinate a release, and prepare a security advisory.
- We will keep you informed at each major step.
- After the fix is released, we may publicly credit your contribution (unless you request anonymity).

## Disclosure Policy

To protect our users, we request a **90‑day embargo** from the date of your initial report before any public disclosure. We will make every effort to release a patch and advisory within that window. If additional time is needed, we will coordinate with you for an extension.

## Scope

This policy covers vulnerabilities in the core project code and its official distribution. Issues in third‑party dependencies should be reported to their respective maintainers. For critical dependencies, we can assist in coordinated disclosure.

## Contact

- **Email**: security@example.com  
- **PGP Key**: Available at `https://example.com/security.asc` (fingerprint: `ABCD 1234 5678 90EF ...`)  
- **GitHub**: If your repository uses GitHub Private Vulnerability Reporting, we encourage that as an alternative to email.

## Acknowledgments

We value the contributions of security researchers who help keep our community safe. Thank you for your responsible disclosure and partnership.

---

*This policy is adapted from best practices used by major open source projects and is reviewed periodically.*