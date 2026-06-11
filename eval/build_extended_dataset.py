"""Build the extended (300+) deterministic evaluation dataset.

Parses the real generated OneNote pages (generated_onenote_pages/) into an
offline retrieval corpus and pairs it with ~310 hand-authored test cases in
five categories:

  * answerable  - direct fact, procedural and paraphrase questions per page
  * attachment  - questions answerable only from indexed .md attachments
  * refusal     - questions about knowledge absent from the corpus
  * clarify     - deliberately ambiguous questions matching several pages
  * hedge       - near-miss questions adjacent to existing pages
  * acl         - allow/deny persona pairs over restricted pages

Outputs:
  eval/datasets/extended_corpus.json
  eval/datasets/extended_eval.json

Run:  python eval/build_extended_dataset.py
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES_ROOT = HERE.parent / "generated_onenote_pages"
OUT_CORPUS = HERE / "datasets" / "extended_corpus.json"
OUT_EVAL = HERE / "datasets" / "extended_eval.json"

HEADINGS = {
    "Context", "Overview", "Summary", "Purpose", "Owner and Systems", "Ownership",
    "Key Facts", "Onboarding Steps", "How We Apply It", "Setup Process",
    "Deployment Process", "Investigation Steps", "Request Flow", "Support Process",
    "Employee Process", "Approval Process", "Control Process", "Commands",
    "Attachments", "Systems Involved", "What To Keep", "Owner", "For", "Systems",
}
STEP_HEADINGS = {
    "Onboarding Steps", "How We Apply It", "Setup Process", "Deployment Process",
    "Investigation Steps", "Request Flow", "Support Process", "Employee Process",
    "Approval Process", "Control Process",
}

DEFAULT_PERSONA = ["public", "employees"]


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._skip += 1
        if tag in ("h1", "h2", "h3", "p", "li", "tr", "dt", "dd", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _page_lines(path: Path) -> list[str]:
    parser = _Text()
    parser.feed(path.read_text(encoding="utf-8"))
    return [line.strip() for line in "".join(parser.parts).splitlines() if line.strip()]


def _sections(lines: list[str]) -> tuple[str, list[str], list[str]]:
    """Return (summary, key_facts, steps) parsed from a page's text lines."""
    summary = lines[2] if len(lines) > 2 else ""
    facts: list[str] = []
    steps: list[str] = []
    current: str | None = None
    for line in lines[3:]:
        if line in HEADINGS:
            current = line
            continue
        if current == "Key Facts":
            facts.append(line)
        elif current in STEP_HEADINGS:
            steps.append(line)
    return summary, facts, steps


def _sentence(value: str) -> str:
    value = value.strip()
    return value if value.endswith((".", "!", "?")) else value + "."


# page spec: id -> (section_dir, html_stem, acl_tags, [(category, question, [terms])])
P = {
 "p0101": ("01_Onboarding", "01_First_Week_Plan_for_New_Engineers", None, [
    ("direct", "What should a new engineer accomplish in their first week?", ["laptop", "buddy"]),
    ("direct", "How quickly are accounts provisioned after the IT ticket on day one?", ["4 business hours"]),
    ("procedural", "What are the first onboarding steps for a new engineer?", ["laptop", "sso"]),
    ("paraphrase", "I just joined as a developer - what is expected of me in my first few days?", ["buddy"]),
    ("direct", "When must security awareness training be completed?", ["5 days"]),
 ]),
 "p0102": ("01_Onboarding", "02_Developer_Workstation_Setup", None, [
    ("direct", "What is the standard developer toolchain for workstation setup?", ["node.js 20", "python 3.12"]),
    ("direct", "What is the internal package registry and how do I authenticate to it?", ["registry.northwind.local"]),
    ("procedural", "How do I set up my developer workstation?", ["install", "signing"]),
    ("paraphrase", "Which programs must be on my machine before I start coding on a project?", ["git"]),
 ]),
 "p0103": ("01_Onboarding", "03_Accounts_and_Access_on_Day_One", None, [
    ("direct", "Which accounts are provisioned automatically on day one?", ["sso", "slack", "github"]),
    ("direct", "Can a new hire get production access on day one?", ["never granted", "security approval"]),
    ("procedural", "How do I request team-specific tool access as a new hire?", ["access portal"]),
    ("paraphrase", "What logins will already work when I first sign in at the company?", ["sso"]),
 ]),
 "p0104": ("01_Onboarding", "04_Team_Rituals_and_Cadence", None, [
    ("direct", "When does the daily standup start and how long does it last?", ["10:00", "15 minutes"]),
    ("direct", "How long are sprints and when do they start?", ["two-week", "wednesdays"]),
    ("procedural", "What should I do if I cannot attend standup live?", ["before 10:00"]),
    ("paraphrase", "Which recurring meetings should a newcomer put in their calendar?", ["standup"]),
    ("direct", "When do sprint review and retro happen?", ["second tuesday"]),
 ]),
 "p0105": ("01_Onboarding", "05_First_Month_Milestones", None, [
    ("direct", "What milestones should an engineer hit by day 30?", ["five pull requests", "staging"]),
    ("direct", "When can a new engineer start on-call shadowing?", ["manager review", "shadowing"]),
    ("procedural", "How are first month milestones tracked?", ["1:1"]),
    ("paraphrase", "What does being fully ramped up look like after four weeks?", ["pull requests"]),
 ]),
 "p0106": ("01_Onboarding", "06_Onboarding_Buddy_Responsibilities", None, [
    ("direct", "Who can be an onboarding buddy?", ["peer engineer"]),
    ("direct", "How much time does an onboarding buddy commit?", ["3 hours per week"]),
    ("procedural", "What does the buddy do for the new hire's first ticket?", ["pair"]),
    ("paraphrase", "What support am I supposed to get from the colleague assigned to me when I join?", ["buddy"]),
 ]),
 "p0201": ("02_Engineering_Handbook", "01_Git_Branching_and_Pull_Request_Workflow", None, [
    ("direct", "What branching model do we use?", ["trunk-based"]),
    ("direct", "How many approvals does a pull request need?", ["one approval", "two approvals"]),
    ("procedural", "What is the pull request workflow from branch to merge?", ["draft", "squash-merge"]),
    ("paraphrase", "I finished my code change - how do I get it into the main branch?", ["pull request"]),
    ("direct", "How long can a branch sit idle before it is deleted?", ["30 days"]),
 ]),
 "p0202": ("02_Engineering_Handbook", "02_Code_Review_Standards", None, [
    ("direct", "What is the expected turnaround for code reviews?", ["one business day"]),
    ("direct", "What do reviewers check first in a code review?", ["correctness"]),
    ("procedural", "How should I review a pull request properly?", ["ticket", "tests"]),
    ("paraphrase", "My PR has been sitting without review since yesterday morning - what does policy say?", ["one business day"]),
 ]),
 "p0203": ("02_Engineering_Handbook", "03_Coding_Standards_and_Formatting", None, [
    ("direct", "Which formatters and linters are enforced?", ["ruff", "prettier"]),
    ("direct", "What is the maximum line length?", ["100"]),
    ("procedural", "How do I set up the linting hooks locally?", ["pre-commit install"]),
    ("paraphrase", "Will the build fail if my code is badly formatted?", ["blocks merge"]),
 ]),
 "p0204": ("02_Engineering_Handbook", "04_Architecture_Decision_Records", None, [
    ("direct", "When should I write an ADR?", ["costly to reverse"]),
    ("direct", "What are the four parts of an ADR?", ["context", "consequences"]),
    ("procedural", "What is the process to get an ADR accepted?", ["template", "architecture review"]),
    ("paraphrase", "We're choosing a new database - do we need to document that decision somewhere?", ["adr"]),
 ]),
 "p0205": ("02_Engineering_Handbook", "05_Testing_Strategy", None, [
    ("direct", "What is the code coverage target?", ["80%"]),
    ("direct", "When do integration and end-to-end tests run?", ["merge to main", "nightly"]),
    ("procedural", "What tests must I add for a new external dependency?", ["integration test"]),
    ("paraphrase", "A test fails randomly on every third CI run - what is the procedure?", ["quarantined"]),
    ("paraphrase", "What happens to a flaky test?", ["quarantined"]),
 ]),
 "p0206": ("02_Engineering_Handbook", "06_Naming_Conventions", None, [
    ("direct", "What is the rule for naming conventions in repositories?", ["kebab-case"]),
    ("direct", "How are environment variables named?", ["upper_snake_case"]),
    ("procedural", "Where do I check before naming something new?", ["catalog"]),
    ("paraphrase", "Is there a standard format for feature flag names?", ["area.flag-name"]),
 ]),
 "p0301": ("03_Project_Setups", "01_Billing_Service_Setup", None, [
    ("direct", "What stack is billing-service built on?", ["fastapi", "postgresql"]),
    ("direct", "What port does billing-service run on locally?", ["8020"]),
    ("procedural", "How do I set up billing-service locally?", ["virtualenv", "vault"]),
    ("paraphrase", "Where do I get the Stripe test credentials for local development?", ["secret/billing/stripe-test"]),
 ]),
 "p0302": ("03_Project_Setups", "02_Web_App_Setup", None, [
    ("direct", "What framework is the customer web app built with?", ["react 19", "vite"]),
    ("direct", "What port does the web app dev server use?", ["5173"]),
    ("procedural", "How do I run the web app locally?", ["npm"]),
    ("paraphrase", "Which testing tools cover the frontend, both unit and end to end?", ["vitest", "playwright"]),
 ]),
 "p0303": ("03_Project_Setups", "03_Search_Service_Setup", None, [
    ("direct", "What language and engine does search-service use?", ["go", "opensearch"]),
    ("direct", "How do I rebuild the search index?", ["reindex", "catalog"]),
    ("procedural", "How do I set up search-service locally?", ["docker compose", "make"]),
    ("paraphrase", "Which endpoint tells me whether the search backend is alive?", ["/healthz"]),
 ]),
 "p0304": ("03_Project_Setups", "04_Data_Pipeline_Setup", None, [
    ("direct", "What orchestrates the analytics data pipeline?", ["airflow"]),
    ("direct", "What do the dbt models build into locally?", ["duckdb"]),
    ("procedural", "How do I run the daily ETL locally?", ["daily_etl"]),
    ("paraphrase", "Where does local source data for the pipeline come from?", ["fixtures"]),
 ]),
 "p0305": ("03_Project_Setups", "05_Mobile_App_Setup", None, [
    ("direct", "What is the supported Flutter version?", ["3.24"]),
    ("direct", "Which API does the mobile app target by default?", ["staging"]),
    ("procedural", "How do I set up the mobile app project?", ["flutter doctor"]),
    ("paraphrase", "How do we make sure key screens keep rendering exactly the same?", ["golden tests"]),
 ]),
 "p0306": ("03_Project_Setups", "06_Internal_CLI_Setup", None, [
    ("direct", "What does the nw CLI do?", ["bootstraps"]),
    ("direct", "What does nw doctor validate?", ["registry auth"]),
    ("procedural", "How do I install the nw command-line tool?", ["internal mirror"]),
    ("paraphrase", "Is there a company tool that checks my environment is healthy?", ["doctor"]),
 ]),
 "p0401": ("04_Releases_and_Deployment", "01_Production_Release_Process", None, [
    ("direct", "How does a change get deployed to production?", ["staging soak"]),
    ("direct", "Can we deploy on the weekend?", ["freeze", "hotfix"]),
    ("procedural", "What are the steps of a production rollout?", ["canary"]),
    ("paraphrase", "What share of traffic does a new release get at first?", ["5%"]),
    ("direct", "Who must be named before a rollout starts?", ["rollback owner"]),
 ]),
 "p0402": ("04_Releases_and_Deployment", "02_Rollback_Procedure", None, [
    ("direct", "How do I roll back a bad production release?", ["last-stable"]),
    ("direct", "Are database migrations safe for rollback?", ["backward compatible"]),
    ("procedural", "What is the rollback procedure during an incident?", ["incident channel"]),
    ("paraphrase", "A release broke production - what's the fastest way to restore the previous version?", ["last-stable"]),
 ]),
 "p0403": ("04_Releases_and_Deployment", "03_Feature_Flag_Management", None, [
    ("direct", "How are feature flags managed for releases?", ["off in production"]),
    ("direct", "How are risky flags rolled out?", ["internal users", "10%"]),
    ("procedural", "What is the lifecycle of a feature flag?", ["owner and expiry"]),
    ("paraphrase", "After my feature is fully live, what happens to its toggle?", ["60 days"]),
 ]),
 "p0404": ("04_Releases_and_Deployment", "04_Staging_Environment_Policy", None, [
    ("direct", "What is the staging environment policy?", ["mirrors production"]),
    ("direct", "Can I run load tests on staging?", ["booking a window"]),
    ("procedural", "What do I do after deploying my change to staging?", ["smoke"]),
    ("paraphrase", "Does staging talk to mocked external services?", ["sandboxes"]),
 ]),
 "p0405": ("04_Releases_and_Deployment", "05_Release_Notes_and_Changelog", None, [
    ("direct", "How are customer release notes produced?", ["changelog"]),
    ("direct", "When are release notes published?", ["second wednesday"]),
    ("procedural", "What must I do for a customer-facing PR to appear in release notes?", ["label"]),
    ("paraphrase", "We're shipping a breaking API change - what notice do customers get?", ["30 days"]),
 ]),
 "p0501": ("05_Runbooks_and_Troubleshooting", "01_High_API_Latency_Runbook", None, [
    ("direct", "When does the latency alert fire?", ["800 ms", "5 minutes"]),
    ("direct", "What is the most common cause of high API latency?", ["connection pool"]),
    ("procedural", "What do I check first during an API latency incident?", ["dashboard"]),
    ("paraphrase", "API responses are slow - what's the standard first mitigation?", ["6 replicas"]),
 ]),
 "p0502": ("05_Runbooks_and_Troubleshooting", "02_Failed_Deployment_Runbook", None, [
    ("direct", "What happens when a deployment fails health checks?", ["halts"]),
    ("direct", "Does a failed deploy take down the running version?", ["old pods"]),
    ("procedural", "How do I investigate a failed deployment?", ["pipeline logs"]),
    ("paraphrase", "Deployment went red and I'm not sure why - should I debug it live?", ["last-stable"]),
 ]),
 "p0503": ("05_Runbooks_and_Troubleshooting", "03_Database_Connection_Errors", None, [
    ("direct", "What is the database max_connections limit?", ["400"]),
    ("direct", "How does a connection leak show up?", ["idle-in-transaction"]),
    ("procedural", "How do I resolve too many connections errors?", ["pg_stat_activity"]),
    ("paraphrase", "What happens to queries that run longer than half a minute?", ["watchdog"]),
    ("paraphrase", "What pools client connections in front of Postgres?", ["pgbouncer"]),
 ]),
 "p0504": ("05_Runbooks_and_Troubleshooting", "04_Docker_Compose_Port_Conflict", None, [
    ("direct", "How to fix a Docker Compose port conflict?", ["stale container"]),
    ("direct", "How do I free a port held by old containers?", ["orphaned"]),
    ("procedural", "What are the steps to resolve the port is already allocated error?", ["holds the port"]),
    ("paraphrase", "Postgres won't start locally because something is squatting on 5432 - now what?", ["5432"]),
 ]),
 "p0505": ("05_Runbooks_and_Troubleshooting", "05_Vector_Search_Returns_No_Results", None, [
    ("direct", "Why does vector search return no results?", ["dimension", "reindex"]),
    ("direct", "What must the collection vector size match?", ["embedding model dimension"]),
    ("procedural", "How do I diagnose an empty semantic search result?", ["point count"]),
    ("paraphrase", "Semantic queries suddenly come back empty after we switched embedding models - why?", ["reindex"]),
 ]),
 "p0601": ("06_Internal_Tools_and_Access", "01_GitHub_Access_and_Teams", None, [
    ("direct", "How do I get access to our GitHub repositories?", ["github teams"]),
    ("direct", "What does write access to infra repos require?", ["security approval"]),
    ("procedural", "What is the flow to join a GitHub team?", ["access portal"]),
    ("paraphrase", "Can a repo admin just add my personal account directly?", ["never to individuals"]),
 ]),
 "p0602": ("06_Internal_Tools_and_Access", "02_Secrets_Vault_Usage", None, [
    ("direct", "Where should application secrets be stored?", ["hashicorp vault"]),
    ("direct", "How often do production secrets rotate?", ["90 days"]),
    ("procedural", "How do I read a secret for my service?", ["sso token"]),
    ("paraphrase", "Is it ever OK to put a password in the repository?", ["never committed"]),
 ]),
 "p0603": ("06_Internal_Tools_and_Access", "03_CI_Pipeline_Access_and_Reruns", None, [
    ("direct", "Where does CI run and on what runners?", ["github actions", "self-hosted"]),
    ("direct", "Who can rerun a failed CI job?", ["anyone"]),
    ("procedural", "How do I rerun a failed CI job?", ["actions tab"]),
    ("paraphrase", "My pipeline job has been queued forever - what does that usually mean?", ["no runner"]),
 ]),
 "p0604": ("06_Internal_Tools_and_Access", "04_Observability_Stack_Access", None, [
    ("direct", "Where are the dashboards and how do I access them?", ["grafana", "sso"]),
    ("direct", "Where are logs queried?", ["loki"]),
    ("procedural", "How do I run an ad-hoc log query?", ["explore"]),
    ("paraphrase", "I need to follow a request across services - which tool shows traces?", ["tempo"]),
 ]),
 "p0605": ("06_Internal_Tools_and_Access", "05_Jira_Projects_and_Boards", None, [
    ("direct", "How are Jira projects organized?", ["short code"]),
    ("direct", "What is the ticket workflow?", ["backlog", "done"]),
    ("procedural", "How do I get access to a Jira board?", ["access portal"]),
    ("paraphrase", "Two teams share work on one feature - do we move tickets between their projects?", ["linked issues"]),
 ]),
 "p0701": ("07_IT_Support", "01_VPN_Access_and_Recovery", None, [
    ("direct", "How do I connect to the corporate VPN?", ["anyconnect"]),
    ("direct", "What if my VPN certificate is invalid?", ["reinstall the profile"]),
    ("procedural", "What are the steps to recover VPN access?", ["mfa push"]),
    ("paraphrase", "Do I need the tunnel running for everyday SaaS tools?", ["admin networks"]),
 ]),
 "p0702": ("07_IT_Support", "02_MFA_Device_Replacement", None, [
    ("direct", "How do I re-enroll MFA after getting a new phone?", ["video confirmation"]),
    ("direct", "How long do I have to enroll the new device after an MFA reset?", ["24 hours"]),
    ("procedural", "What is the MFA reset process?", ["service desk ticket"]),
    ("paraphrase", "I lost my phone with the authenticator app - who resets it?", ["service desk"]),
 ]),
 "p0703": ("07_IT_Support", "03_Laptop_Replacement_and_Repair", None, [
    ("direct", "How fast are replacement laptops shipped?", ["2 business days"]),
    ("direct", "What must I do if my laptop is lost?", ["1 hour"]),
    ("procedural", "What is the process for replacing a broken laptop?", ["service desk"]),
    ("paraphrase", "Is company data exposed if a machine goes missing?", ["encrypted"]),
 ]),
 "p0704": ("07_IT_Support", "04_Software_Installation_Requests", None, [
    ("direct", "How do I install software outside the standard image?", ["self-service portal"]),
    ("direct", "Can engineers install developer tools without a ticket?", ["without a ticket"]),
    ("procedural", "What is the request process for non-standard software?", ["business reason"]),
    ("paraphrase", "Why won't this random downloaded app run on my laptop?", ["blocked"]),
 ]),
 "p0705": ("07_IT_Support", "05_Email_and_Distribution_Lists", None, [
    ("direct", "How do I request a distribution list?", ["owner"]),
    ("direct", "What naming pattern do distribution lists follow?", ["northwind.local"]),
    ("procedural", "What are the steps to create a new mailing list?", ["access portal"]),
    ("paraphrase", "What happens when someone outside the company emails an internal list?", ["quarantined"]),
 ]),
 "p0801": ("08_People_and_HR", "01_Paid_Time_Off_Policy", None, [
    ("direct", "How many days of annual leave do employees get?", ["25 days"]),
    ("direct", "How much unused leave carries over?", ["31 march"]),
    ("procedural", "How do I request time off?", ["hr portal"]),
    ("paraphrase", "Planning a two-week vacation - how early must I ask?", ["3 weeks"]),
    ("paraphrase", "When do carried-over vacation days expire?", ["31 march"]),
 ]),
 "p0802": ("08_People_and_HR", "02_Remote_and_Hybrid_Work", None, [
    ("direct", "What is the hybrid work policy?", ["2 days"]),
    ("direct", "What are core collaboration hours?", ["10:00 to 16:00"]),
    ("procedural", "How do I become fully remote?", ["vp approval"]),
    ("paraphrase", "I want to work from another country all summer - is that fine?", ["tax"]),
 ]),
 "p0803": ("08_People_and_HR", "03_On_Call_Compensation", ["hr"], [
    ("direct", "What is the on-call compensation?", ["stipend"]),
    ("direct", "What do I get if paged after midnight?", ["late start"]),
    ("procedural", "What should I record during my on-call week?", ["night pages"]),
    ("paraphrase", "Is there extra pay for carrying the pager for a week?", ["stipend"]),
 ]),
 "p0804": ("08_People_and_HR", "04_Performance_Review_Cycle", ["hr"], [
    ("direct", "When do performance reviews run?", ["june", "december"]),
    ("direct", "What inputs go into a performance review?", ["self-assessment", "peer"]),
    ("procedural", "What do I do during the review cycle?", ["self-assessment"]),
    ("paraphrase", "When can promotion cases be submitted?", ["december"]),
 ]),
 "p0805": ("08_People_and_HR", "05_Health_Insurance_and_Benefits_Enrollment", None, [
    ("direct", "How long do new hires have to enroll in health insurance?", ["30 days"]),
    ("direct", "How much of the premium does the company cover?", ["100%", "60%"]),
    ("procedural", "How do I enroll in benefits?", ["benefits portal"]),
    ("paraphrase", "I got married - can I change my plan mid-year?", ["qualifying life event"]),
 ]),
 "p0806": ("08_People_and_HR", "06_Learning_and_Development_Budget", None, [
    ("direct", "How big is the annual learning budget?", ["1,500"]),
    ("direct", "What is eligible under the learning budget?", ["conferences", "certifications"]),
    ("procedural", "How do I use my training budget?", ["manager approval"]),
    ("paraphrase", "If I don't spend my education money this year, do I keep it?", ["does not carry over"]),
 ]),
 "p0901": ("09_Finance_and_Procurement", "01_Expense_Reimbursement", None, [
    ("direct", "How do I claim work-related expenses?", ["expense tool", "60 days"]),
    ("direct", "When is a receipt mandatory?", ["25 eur"]),
    ("procedural", "What are the steps to submit an expense?", ["receipt", "cost center"]),
    ("paraphrase", "Team dinner included a bottle of wine - will that be paid back?", ["alcohol"]),
 ]),
 "p0902": ("09_Finance_and_Procurement", "02_Software_and_SaaS_Purchasing", None, [
    ("direct", "What is required before buying a new SaaS tool?", ["security"]),
    ("direct", "Who approves purchases over 5,000 EUR?", ["finance director"]),
    ("procedural", "How do I request a new software purchase?", ["business case"]),
    ("paraphrase", "We found a new vendor nobody has used before - what's the gate?", ["security review"]),
 ]),
 "p0903": ("09_Finance_and_Procurement", "03_Cloud_Cost_Management", None, [
    ("direct", "What tags must cloud resources carry?", ["environment tags"]),
    ("direct", "What happens to untagged resources?", ["7 days"]),
    ("procedural", "What do I do when a spend anomaly alert fires?", ["investigate"]),
    ("paraphrase", "Do dev environments run at full size overnight?", ["working hours"]),
 ]),
 "p0904": ("09_Finance_and_Procurement", "04_Vendor_Invoice_Processing", ["finance"], [
    ("direct", "How are supplier invoices received?", ["invoice portal"]),
    ("direct", "What are the standard payment terms?", ["net 30"]),
    ("procedural", "How is an invoice approved for payment?", ["purchase order"]),
    ("paraphrase", "An invoice doesn't match its order - what happens?", ["hold"]),
 ]),
 "p0905": ("09_Finance_and_Procurement", "05_Team_Budget_and_Forecast", ["finance"], [
    ("direct", "Give me info about the team budget process", ["annually", "quarter"]),
    ("direct", "What budget variance requires a written explanation?", ["10%"]),
    ("procedural", "How do managers track their budget?", ["actuals"]),
    ("paraphrase", "Laptops we buy - are they counted like normal monthly spend?", ["depreciated"]),
 ]),
 "p1001": ("10_Security_and_Compliance", "01_Data_Classification_Policy", None, [
    ("direct", "What are the data classification levels?", ["public", "restricted"]),
    ("direct", "Can payment card data be stored in logs?", ["never"]),
    ("procedural", "How do I apply the classification rules?", ["highest class"]),
    ("paraphrase", "How should customer PII be treated by default?", ["confidential"]),
    ("paraphrase", "Which data class applies to payment card numbers?", ["restricted"]),
 ]),
 "p1002": ("10_Security_and_Compliance", "02_Security_Incident_Response", ["security"], [
    ("direct", "What do I do when I suspect a security incident?", ["30 minutes"]),
    ("direct", "Can I delete logs after an incident?", ["preserve"]),
    ("procedural", "What is the incident reporting process?", ["security channel"]),
    ("paraphrase", "Someone's laptop seems compromised - who coordinates the response?", ["security engineer"]),
 ]),
 "p1003": ("10_Security_and_Compliance", "03_Access_Reviews", ["security"], [
    ("direct", "How often is production access reviewed?", ["quarter"]),
    ("direct", "What happens if access is not confirmed in time?", ["automatically revoked"]),
    ("procedural", "What does a manager do in an access review?", ["confirm or revoke"]),
    ("paraphrase", "Are robot accounts audited like human ones?", ["service accounts"]),
 ]),
 "p1004": ("10_Security_and_Compliance", "04_Secure_Coding_Guidelines", None, [
    ("direct", "How should SQL queries be built safely?", ["parameterized"]),
    ("direct", "What blocks a merge from dependency scanning?", ["high-severity"]),
    ("procedural", "What are the baseline secure coding practices?", ["parameterized queries"]),
    ("paraphrase", "User-supplied text goes straight into a query string - acceptable?", ["concatenation"]),
 ]),
 "p1005": ("10_Security_and_Compliance", "05_Vendor_Risk_and_SOC_2_Evidence", ["security"], [
    ("direct", "What must new vendors handling customer data provide?", ["soc 2 type ii"]),
    ("direct", "How is SOC 2 evidence collected?", ["continuously"]),
    ("procedural", "How do I handle a new vendor's risk review?", ["risk register"]),
    ("paraphrase", "What kind of access do external auditors get?", ["read-only"]),
 ]),
}

SECTION_ACL = {
    "01_Onboarding": ["public", "employees"],
    "02_Engineering_Handbook": ["employees", "engineering"],
    "03_Project_Setups": ["employees", "engineering"],
    "04_Releases_and_Deployment": ["employees", "engineering"],
    "05_Runbooks_and_Troubleshooting": ["employees", "engineering"],
    "06_Internal_Tools_and_Access": ["employees", "engineering"],
    "07_IT_Support": ["public", "employees"],
    "08_People_and_HR": ["public", "employees"],
    "09_Finance_and_Procurement": ["employees", "finance"],
    "10_Security_and_Compliance": ["public", "employees"],
}

# attachment .md docs: id -> (section_dir, md filename, parent page id, (question, terms))
ATTACHMENTS = {
 "att0102": ("01_Onboarding", "02_Developer_Workstation_Setup__workstation-checklist.md", "p0102",
             ("What does the workstation checklist say about Docker memory?", ["8 gb"])),
 "att0203": ("02_Engineering_Handbook", "03_Coding_Standards_and_Formatting__coding-standards.md", "p0203",
             ("What does the coding standards attachment say about Python type checking?", ["mypy"])),
 "att0301": ("03_Project_Setups", "01_Billing_Service_Setup__billing-service-readme.md", "p0301",
             ("What does the billing-service readme list as key commands?", ["alembic"])),
 "att0501": ("05_Runbooks_and_Troubleshooting", "01_High_API_Latency_Runbook__api-latency-runbook.md", "p0501",
             ("What does the condensed latency runbook tell paging engineers to check first?", ["db pool"])),
}

REFUSAL_PROBES = [
    "What is the parental leave policy and how long is it?",
    "What are the salary bands for senior engineers?",
    "How does stock option vesting work here?",
    "Is there parking at the office and how do I get a spot?",
    "What is on the cafeteria menu this week?",
    "Does the company sponsor work visas?",
    "Is there a sabbatical program after five years?",
    "What relocation package is offered to new hires?",
    "Can I get a company car through work?",
    "Are dogs allowed in the office?",
    "Is there a dress code for client meetings?",
    "What percentage does the company match into the pension plan?",
    "Is there a gym membership subsidy?",
    "Which tool do we use to book business travel?",
    "How do I set up the office printer?",
    "What is the guest wifi password?",
    "What is the street address of the headquarters?",
    "Which public holidays does the company observe this year?",
    "How much is the employee referral bonus?",
    "How do I replace a lost office badge?",
    "How do I book a meeting room?",
    "What is the policy for jury duty?",
    "How many days of bereavement leave do we get?",
    "How is overtime compensated for non-engineers?",
    "Does the company run a summer internship program?",
    "Is tuition for a part-time master's degree reimbursed?",
    "Does the company match charitable donations?",
    "Is there a mobile phone stipend?",
    "Is home internet reimbursed for remote workers?",
    "Do I need a doctor's note for two sick days?",
    "What is the notice period when resigning?",
    "How long is the probation period for new employees?",
]

CLARIFY_PROBES = [
    "How do I get access?",
    "How do I set up the app?",
    "The service is failing, what should I check?",
    "What's the approval process?",
    "How do I run the tests?",
    "Where do I find the dashboard?",
    "What's the deployment process?",
    "Who approves my request?",
    "How do I reset it?",
    "What port does the service use?",
    "How do I get the secrets?",
    "What's the review process?",
    "How do I report a problem?",
    "What's the budget?",
    "How do I install it?",
    "I'm getting a connection error, what now?",
]

HEDGE_PROBES = [
    "How are medical claims submitted?",
    "Can I expense a gym membership?",
    "What is the sick leave policy?",
    "How do I rotate my SSH keys?",
    "How do I get access to the Kubernetes cluster?",
    "How do I reset my LDAP password?",
    "What is the database backup schedule?",
    "What are the API rate limits for external clients?",
    "What is the SLA for customer support tickets?",
    "How do I encrypt a USB stick?",
    "What are the rules for creating new Slack channels?",
    "How do we handle GDPR data deletion requests?",
    "What are the password complexity requirements?",
    "When are Windows updates forced on laptops?",
    "Do I need approval to speak at a conference?",
    "How do I transfer to another team internally?",
]

# restricted page id -> (question, restricted tag)
ACL_ABLATION = {
    "p0803": ("What is the on-call compensation stipend?", "hr"),
    "p0804": ("When does the performance review cycle run?", "hr"),
    "p0904": ("How are supplier invoices processed and paid?", "finance"),
    "p0905": ("What is the team budget and forecast process?", "finance"),
    "p1002": ("What are the steps of the security incident response?", "security"),
    "p1003": ("How do quarterly access reviews work?", "security"),
    "p1005": ("How is SOC 2 audit evidence organized?", "security"),
}


def _persona(acl_tags: list[str]) -> dict:
    tags = list(DEFAULT_PERSONA)
    for tag in acl_tags:
        if tag not in ("public", "employees", "engineering") and tag not in tags:
            tags.append(tag)
    return {
        "user_id": "eval-employee",
        "email": "employee@example.com",
        "tenant_id": "local-tenant",
        "acl_tags": tags,
    }


def build() -> None:
    documents: list[dict] = []
    answerable: list[dict] = []

    for page_id, (section_dir, stem, acl_override, questions) in P.items():
        path = PAGES_ROOT / section_dir / f"{stem}.html"
        lines = _page_lines(path)
        title = lines[0]
        summary, facts, steps = _sections(lines)
        section_name = section_dir.split("_", 1)[1].replace("_", " ")
        acl = acl_override or SECTION_ACL[section_dir]
        base = {
            "source_item_id": page_id,
            "title": title,
            "section_path": f"{section_name} / {title}",
            "acl_tags": acl,
            "tags": [section_name.lower().replace(" ", "-")],
            "metadata": {"notebook_name": "Company Knowledge", "section_name": section_name},
        }
        chunk0 = " ".join([_sentence(summary)] + [_sentence(f) for f in facts[:3]])
        documents.append({**base, "chunk_index": 0, "chunk_text": chunk0})
        if facts[3:]:
            documents.append({
                **base, "chunk_index": 1,
                "chunk_text": " ".join(_sentence(f) for f in facts[3:]),
            })
        if steps:
            documents.append({
                **base, "chunk_index": 2,
                "chunk_text": "How this is done: " + " ".join(_sentence(s) for s in steps),
            })

        for i, (category, question, terms) in enumerate(questions, start=1):
            answerable.append({
                "case_id": f"{page_id}-q{i}",
                "category": category,
                "question": question,
                "expected_source_item_ids": [page_id],
                "expected_answer_terms": terms,
                "user_context": _persona(acl),
                "top_k": 5,
            })

    for att_id, (section_dir, filename, parent, (question, terms)) in ATTACHMENTS.items():
        path = PAGES_ROOT / section_dir / filename
        text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8").replace("#", " ")).strip()
        section_name = section_dir.split("_", 1)[1].replace("_", " ")
        title = filename.split("__", 1)[1].removesuffix(".md").replace("-", " ")
        documents.append({
            "source_item_id": att_id,
            "title": f"Attachment: {title}",
            "section_path": f"{section_name} / {title}",
            "acl_tags": SECTION_ACL[section_dir],
            "chunk_index": 0,
            "chunk_text": text,
            "tags": [section_name.lower().replace(" ", "-"), "attachment"],
            "metadata": {
                "notebook_name": "Company Knowledge",
                "section_name": section_name,
                "parent_source_item_id": parent,
            },
        })
        answerable.append({
            "case_id": f"{att_id}-q1",
            "category": "attachment",
            "question": question,
            "expected_source_item_ids": [att_id, parent],
            "expected_answer_terms": terms,
            "user_context": _persona(SECTION_ACL[section_dir]),
            "top_k": 5,
        })

    probes = (
        [{"case_id": f"refusal-{i:02d}", "category": "refusal", "question": q,
          "acl_tags": DEFAULT_PERSONA} for i, q in enumerate(REFUSAL_PROBES, 1)]
        + [{"case_id": f"clarify-{i:02d}", "category": "clarify", "question": q,
            "acl_tags": DEFAULT_PERSONA} for i, q in enumerate(CLARIFY_PROBES, 1)]
        + [{"case_id": f"hedge-{i:02d}", "category": "hedge", "question": q,
            "acl_tags": DEFAULT_PERSONA} for i, q in enumerate(HEDGE_PROBES, 1)]
    )

    acl_ablation = [
        {
            "case_id": f"acl-{page_id}",
            "question": question,
            "target_source_item_id": page_id,
            "denied_acl_tags": DEFAULT_PERSONA,
            "allowed_acl_tags": DEFAULT_PERSONA + [tag],
        }
        for page_id, (question, tag) in ACL_ABLATION.items()
    ]

    OUT_CORPUS.write_text(json.dumps({
        "name": "extended-eval-corpus-v1",
        "description": "Offline corpus built from the real generated OneNote pages "
                       "(54 pages + 4 readable .md attachments) by eval/build_extended_dataset.py.",
        "documents": documents,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    total = len(answerable) + len(probes) + 2 * len(acl_ablation)
    OUT_EVAL.write_text(json.dumps({
        "name": "extended-eval-v1",
        "description": "Extended deterministic evaluation: answerable, refusal, clarify, "
                       "hedge and ACL-ablation cases over extended_corpus.json.",
        "total_executions": total,
        "answerable": answerable,
        "probes": probes,
        "acl_ablation": acl_ablation,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"documents: {len(documents)} (from {len(P)} pages + {len(ATTACHMENTS)} attachments)")
    print(f"answerable cases: {len(answerable)}")
    print(f"behaviour probes: {len(probes)}")
    print(f"acl ablation pairs: {len(acl_ablation)} ({2 * len(acl_ablation)} executions)")
    print(f"TOTAL test executions: {total}")


if __name__ == "__main__":
    build()
