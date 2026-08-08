# Security Policy

## Supported versions

| Version | Security support |
| --- | --- |
| `1.0.x` | Supported |
| `< 1.0` | Not supported |

Security fixes are applied to the latest supported patch release. Upgrade to
the newest release before reporting behavior that may already be fixed.

## Report a vulnerability privately

Do not disclose suspected vulnerabilities in public issues, discussions, or
pull requests.

Use one of these private channels:

1. [Open a private GitHub security advisory](https://github.com/HoungDev/fastapi-production-api/security/advisories/new), if private vulnerability reporting is enabled.
2. Email `chukafe0401@gmail.com` with the subject
   `Security report: fastapi-production-api`.

Include:

- affected version or commit SHA;
- vulnerability description and potential impact;
- minimal reproduction steps or proof of concept;
- relevant configuration with credentials and personal data removed;
- whether the issue has been disclosed anywhere else.

Do not include live credentials, access tokens, personal data, or production
database contents. Use synthetic data in proofs of concept.

## Response process

The maintainer will aim to:

1. acknowledge the report within five business days;
2. validate impact and affected versions;
3. coordinate a fix and disclosure timeline with the reporter;
4. publish a patch release and security advisory when appropriate.

Timelines may vary with severity and maintainer availability. Please allow a
reasonable remediation window before public disclosure.

## Security boundaries

The project provides security-focused defaults, but deployers remain
responsible for secrets management, proxy trust, TLS, database access, backups,
distributed rate limiting, dependency updates, monitoring, and their own threat
model. Review the [known limitations](README.md#known-limitations) before
production use.
