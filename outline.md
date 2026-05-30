markdown
# Security Policy

## Supported Versions

We provide security updates exclusively for the **latest major release**. Older major versions are not patched retroactively. Users must upgrade to the most recent major version to receive security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of our project seriously. If you discover a vulnerability, please report it to us **privately and responsibly**. **Do not** file a public issue or disclose the vulnerability before a fix is available.

### Contact

- **Primary email:** security@example.com  
  (Please use a descriptive subject line, e.g., "Security Vulnerability in v1.2.3 – RCE in authentication module")
- **PGP Key:** [Download](https://example.com/pgp-key.asc) – fingerprint: `ABCD 1234 5678 90EF 1234 5678 90AB CDEF 1234 5678`
- **Alternative contact:** If you do not receive a response within 48 hours, please follow up via the same channel or reach out to an active maintainer via [GitHub Security Advisories](https://github.com/example/example/security/advisories). We treat all reports with confidentiality.

### Expected Response Time

We acknowledge receipt of your report within **48 hours**. After that, we provide an initial assessment and a timeline for a fix. If we require additional information, we will ask promptly.

### Report Guidelines

Please include the following details:

- A clear description of the vulnerability.
- Steps to reproduce the issue (including any relevant configurations, versions, and environment details).
- Proof-of-concept code or demonstration (if available).
- Affected versions (e.g., 1.2.0 – 1.2.5).
- Your preferred method of contact (if different from the reporting email) and whether you would like to be credited in public advisory.

### Scope

This policy covers vulnerabilities in the source code, build scripts, and official releases of this project. It does not cover vulnerabilities in third-party dependencies unless they are exploitable through the project’s interfaces. For dependency issues, please report them to the respective upstream maintainers.

## Disclosure Policy

To protect our users and the community, we ask that you **refrain from publicly disclosing the vulnerability** until a fix has been released. The typical embargo period is **90 days** from the date of initial notification. This allows us to develop, test, and distribute a patch.

We will work with you to coordinate a public announcement, crediting you for the discovery (if you choose). If we are unable to address the issue within 90 days, we will inform you and may request an extension or agree on an alternative timeline.

## Security Patch Process

1. **Triage** – We assess the vulnerability and assign a severity level (e.g., using CVSS 3.1).
2. **Development** – A fix is created, tested, and reviewed internally.
3. **Backport** – If applicable, the fix is backported to the latest major version (only).
4. **Release** – A new patch version is published, and the advisory is updated.
5. **Disclosure** – A public advisory is released, including credit to the reporter (if desired).

We strive to release a fix within **14 days** for critical vulnerabilities and within **30 days** for high-severity issues. Timelines for lower-severity issues may be longer.

## Hall of Fame

We maintain a [SECURITY_AWARDS.md](SECURITY_AWARDS.md) file to recognize individuals who have responsibly disclosed vulnerabilities. If you would like to be included, please let us know in your report.

## Questions

For any questions about this policy, please contact security@example.com.

---

*This document is based on best practices from the [Open Source Security Foundation](https://openssf.org/) and follows the format used by major open-source projects.*