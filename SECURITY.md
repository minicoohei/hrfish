# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **GitHub Security Advisories** (preferred): Use [GitHub's private vulnerability reporting](https://github.com/666ghj/MiroFish/security/advisories/new)
2. **Email**: security@mirofish.ai

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **48 hours**: Acknowledgment of your report
- **7 days**: Initial assessment and severity classification
- **30 days**: Fix development and release (for critical/high severity)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |

## Security Best Practices for Deployment

- Always set `MIROFISH_API_KEY` environment variable in production
- Set `SECRET_KEY` to a strong random value
- Configure `CORS_ORIGINS` to your specific domain(s)
- Keep `FLASK_DEBUG=False` in production
- Use HTTPS in production
- Regularly update dependencies
