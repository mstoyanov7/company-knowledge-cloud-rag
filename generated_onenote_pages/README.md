# OneNote Content Pack - Northwind Software

Generated pages: 54
Generated attachments: 19

A generic software-company knowledge base for testing the RAG assistant. Each page
carries concrete, answerable facts (specific numbers, owners, ports, policies) so the
chat returns real answers, not generic prose.

## Sections

1. **Onboarding** - For new-hire orientation, first-week and first-month tasks, accounts, and buddy expectations.
2. **Engineering Handbook** - For engineering standards: branching, code review, formatting, ADRs, testing, and naming.
3. **Project Setups** - For project setup inventory and local setup instructions. Each page title in this section is one project setup. Do not treat tools, runbooks, or deployment pages as project setups.
4. **Releases and Deployment** - For release process, rollout, rollback, feature flags, staging, and release notes.
5. **Runbooks and Troubleshooting** - For symptoms, diagnostics, mitigations, and verification of recurring failures.
6. **Internal Tools and Access** - For access to GitHub, Vault, CI, observability, and Jira.
7. **IT Support** - For helpdesk procedures: VPN, MFA, laptops, software installs, and email.
8. **People and HR** - For leave, remote work, on-call pay, performance reviews, health insurance, and learning budget.
9. **Finance and Procurement** - For expenses, software purchasing, cloud cost, invoices, and team budgets.
10. **Security and Compliance** - For data classification, incident response, access reviews, secure coding, and audits.

## Import into OneNote

1. Create one OneNote section per folder (drop the numeric prefix).
2. For each `.html` file, open it in a browser, copy the rendered page, and paste it into a new OneNote page.
3. For files named `<page>__<attachment>.<ext>`, attach them to that same OneNote page (Insert > File Attachment).
4. Reindex so the app sees the new content:

```powershell
docker compose run --rm --build sync-worker onenote_bootstrap
```

## Attachments

Attachments are real `.md`, `.txt`, `.docx`, `.pptx`, and `.pdf` files. Each contains at
least one fact not repeated verbatim in the page body, so you can verify that attachment
content is retrieved (e.g. ask about a value that only appears in the attached file).
