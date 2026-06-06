from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import shutil


OUTPUT_DIR = Path("generated_onenote_pages_automotive")


@dataclass(frozen=True, slots=True)
class PageSpec:
    title: str
    owner: str
    focus: str
    artifacts: tuple[str, ...]
    systems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SectionSpec:
    name: str
    page_type: str
    audience: str
    count_rule: str
    pages: tuple[PageSpec, ...]


SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(
        name="Project Deployment",
        page_type="deployment guide",
        audience="release managers, DevOps engineers, validation leads",
        count_rule="Do not count these pages as project setup records. These pages describe deployment work.",
        pages=(
            PageSpec(
                "Vehicle Software Release Overview",
                "Release Management",
                "Defines the release scope, release train calendar, and software package boundaries for vehicle software delivery.",
                ("release manifest", "vehicle program scope", "software bill of materials"),
                ("Jira Release Hub", "GitHub Enterprise", "Artifact Registry"),
            ),
            PageSpec(
                "ECU Software Package Matrix",
                "Embedded Platform",
                "Tracks ECU package versions, firmware dependencies, calibration bundles, and compatibility notes before deployment.",
                ("ECU package matrix", "firmware bundle", "calibration mapping"),
                ("Artifactory", "Requirements Traceability", "Vehicle Log Portal"),
            ),
            PageSpec(
                "OTA Campaign Deployment Plan",
                "OTA Operations",
                "Describes staged OTA campaign rollout, target vehicle cohorts, approval gates, and monitoring responsibilities.",
                ("campaign plan", "vehicle cohort list", "rollback threshold"),
                ("OTA Console", "Telemetry Dashboard", "Incident Desk"),
            ),
            PageSpec(
                "Cloud Backend Deployment Readiness",
                "Cloud Platform",
                "Confirms cloud service readiness for automotive backend APIs used by connected vehicle functions.",
                ("deployment checklist", "service dependency map", "API compatibility report"),
                ("Kubernetes", "Service Mesh", "Grafana"),
            ),
            PageSpec(
                "Dealer Diagnostics Rollout",
                "Diagnostics Platform",
                "Explains how diagnostic application updates are released to dealer environments and field service laptops.",
                ("dealer rollout plan", "diagnostic app package", "support bulletin"),
                ("MDM Portal", "Dealer Tool Portal", "Service Desk"),
            ),
            PageSpec(
                "Feature Flag Release Control",
                "Feature Operations",
                "Documents feature flag governance for staged enablement of vehicle, mobile, and cloud capabilities.",
                ("flag register", "enablement plan", "blast radius assessment"),
                ("Feature Flag Console", "Jira", "Telemetry Dashboard"),
            ),
            PageSpec(
                "Production Telemetry Cutover",
                "Data Platform",
                "Covers telemetry pipeline cutover steps when vehicle data streams move from validation to production channels.",
                ("stream mapping", "schema contract", "cutover checklist"),
                ("Kafka", "Data Lake", "Schema Registry"),
            ),
            PageSpec(
                "Manufacturing Plant Deployment Window",
                "Manufacturing IT",
                "Defines deployment windows, freeze periods, and approval contacts for software released to plant systems.",
                ("plant change window", "MES dependency list", "approval record"),
                ("MES", "Plant VPN", "Change Calendar"),
            ),
            PageSpec(
                "Validation and Release Sign-Off",
                "Validation Office",
                "Defines the required evidence and sign-off path before automotive software is approved for release.",
                ("validation report", "test coverage summary", "sign-off record"),
                ("Test Management", "Requirements Traceability", "Jira"),
            ),
            PageSpec(
                "Rollback and Hotfix Procedure",
                "Release Management",
                "Explains rollback decision criteria, hotfix ownership, and communication steps for failed production releases.",
                ("rollback plan", "hotfix branch", "customer impact note"),
                ("GitHub Enterprise", "Incident Desk", "Status Page"),
            ),
        ),
    ),
    SectionSpec(
        name="HR Question",
        page_type="HR policy answer",
        audience="employees, managers, HR partners",
        count_rule="Count these pages as HR policy pages, not as technical projects.",
        pages=(
            PageSpec(
                "Engineering On Call Compensation Rules",
                "People Operations",
                "Summarizes eligibility, approval, and payout rules for engineering on-call duty in production support rotations.",
                ("on-call rota", "manager approval", "payroll adjustment"),
                ("HR Portal", "PagerDuty", "Payroll System"),
            ),
            PageSpec(
                "Remote Work Approval Flow",
                "People Operations",
                "Explains how employees request recurring remote work and how managers approve location exceptions.",
                ("remote work request", "manager approval", "security review"),
                ("HR Portal", "Identity Provider", "Ticket Queue"),
            ),
            PageSpec(
                "Training Budget Request",
                "Learning and Development",
                "Defines how engineers request budget for automotive software training, safety certification, and tooling courses.",
                ("training request", "budget approval", "completion certificate"),
                ("HR Portal", "Finance Approval", "Learning Platform"),
            ),
            PageSpec(
                "Equipment Request Policy",
                "Workplace Services",
                "Documents when employees can request monitors, keyboards, debug adapters, headsets, and ergonomic equipment.",
                ("equipment request", "manager confirmation", "asset record"),
                ("IT Store", "Asset Register", "Service Desk"),
            ),
            PageSpec(
                "Hiring Interview Panel Process",
                "Talent Acquisition",
                "Describes interview panel composition, feedback expectations, and decision timing for engineering roles.",
                ("interview plan", "scorecard", "candidate feedback"),
                ("Applicant Tracking System", "Calendar", "HR Portal"),
            ),
            PageSpec(
                "Contractor Access Onboarding",
                "People Operations",
                "Defines onboarding requirements for contractors who need source code, test bench, or supplier portal access.",
                ("contractor profile", "access request", "end date"),
                ("Identity Provider", "Vendor Portal", "Service Desk"),
            ),
            PageSpec(
                "Travel Expense Eligibility",
                "People Operations",
                "Explains which engineering travel costs are reimbursable for supplier visits, test tracks, and launch support.",
                ("travel request", "expense receipt", "cost center"),
                ("Expense Tool", "Finance Approval", "HR Portal"),
            ),
            PageSpec(
                "Paid Leave During Release Freeze",
                "People Operations",
                "Clarifies how planned leave is handled during release freeze periods and production launch support windows.",
                ("leave request", "coverage plan", "release freeze calendar"),
                ("HR Portal", "Release Calendar", "Team Rota"),
            ),
            PageSpec(
                "Performance Review Timeline",
                "People Operations",
                "Lists the review milestones, calibration steps, and employee input deadlines for engineering teams.",
                ("self review", "manager review", "calibration note"),
                ("HR Portal", "Performance Tool", "Calendar"),
            ),
            PageSpec(
                "Confidential Incident Reporting",
                "People Operations",
                "Explains confidential reporting channels for workplace concerns, ethics issues, and safety-related employee concerns.",
                ("incident report", "confidential channel", "case owner"),
                ("HR Portal", "Ethics Hotline", "Legal Intake"),
            ),
        ),
    ),
    SectionSpec(
        name="Internal Tools",
        page_type="internal tool guide",
        audience="software engineers, validation engineers, project leads",
        count_rule="Count these pages as internal tool guides. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "Jira Project Access",
                "Engineering Operations",
                "Explains how engineers request Jira access for automotive software programs, components, and release boards.",
                ("project key", "role request", "approval ticket"),
                ("Jira", "Identity Provider", "Service Desk"),
            ),
            PageSpec(
                "GitHub Enterprise Repository Access",
                "Developer Platform",
                "Defines repository access tiers, branch protection expectations, and reviewer group ownership.",
                ("repository name", "team slug", "access request"),
                ("GitHub Enterprise", "Identity Provider", "Audit Log"),
            ),
            PageSpec(
                "Artifactory Package Registry",
                "Developer Platform",
                "Documents package publishing, retention, and access rules for firmware, containers, libraries, and test assets.",
                ("package namespace", "retention policy", "publish token"),
                ("Artifactory", "CI Pipeline", "Secrets Vault"),
            ),
            PageSpec(
                "Jenkins Build Farm",
                "Build Infrastructure",
                "Explains how build agents are selected for Linux, Android, QNX, Yocto, and hardware-in-loop jobs.",
                ("agent label", "pipeline job", "build artifact"),
                ("Jenkins", "Artifact Registry", "Test Bench Tool"),
            ),
            PageSpec(
                "SonarQube Quality Dashboard",
                "Quality Engineering",
                "Defines code quality gates, ownership of findings, and release criteria for static analysis results.",
                ("quality gate", "coverage report", "finding owner"),
                ("SonarQube", "GitHub Enterprise", "Jira"),
            ),
            PageSpec(
                "Vehicle Log Portal",
                "Data Platform",
                "Explains how vehicle logs are uploaded, tagged, retained, and searched during validation campaigns.",
                ("VIN alias", "log bundle", "retention class"),
                ("Vehicle Log Portal", "Object Storage", "Data Catalog"),
            ),
            PageSpec(
                "Feature Flag Console",
                "Feature Operations",
                "Documents ownership, approval, and audit rules for feature flags used in connected vehicle releases.",
                ("flag key", "target cohort", "approval record"),
                ("Feature Flag Console", "Telemetry Dashboard", "Jira"),
            ),
            PageSpec(
                "Secrets Vault Access",
                "Security Engineering",
                "Explains how teams request and rotate secrets for test systems, deployment pipelines, and supplier integrations.",
                ("vault path", "secret owner", "rotation date"),
                ("Secrets Vault", "Identity Provider", "CI Pipeline"),
            ),
            PageSpec(
                "Test Bench Reservation Tool",
                "Validation Operations",
                "Defines how teams reserve HIL rigs, ECU benches, vehicles, and lab equipment for validation work.",
                ("bench ID", "reservation slot", "test plan"),
                ("Bench Scheduler", "Lab Inventory", "Calendar"),
            ),
            PageSpec(
                "Requirements Traceability System",
                "Systems Engineering",
                "Explains how software requirements, test cases, defects, and release evidence are linked.",
                ("requirement ID", "test case", "trace link"),
                ("Requirements Traceability", "Test Management", "Jira"),
            ),
        ),
    ),
    SectionSpec(
        name="Finances",
        page_type="finance process",
        audience="engineering managers, project owners, finance partners",
        count_rule="Count these pages as finance process pages. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "Prototype Hardware Purchase Approval",
                "Finance Business Partner",
                "Defines approval flow for ECUs, sensors, harnesses, debug probes, and prototype vehicle hardware.",
                ("purchase request", "supplier quote", "cost center"),
                ("Procurement Portal", "Finance Approval", "Asset Register"),
            ),
            PageSpec(
                "Supplier Invoice Intake",
                "Accounts Payable",
                "Explains how supplier invoices for software services, validation labs, and prototype parts are submitted.",
                ("invoice PDF", "purchase order", "goods receipt"),
                ("Invoice Portal", "ERP", "Procurement Portal"),
            ),
            PageSpec(
                "Engineering Travel Reimbursement",
                "Finance Operations",
                "Defines reimbursement steps for supplier workshops, test track visits, launch support, and certification events.",
                ("travel approval", "receipt bundle", "expense report"),
                ("Expense Tool", "ERP", "Finance Approval"),
            ),
            PageSpec(
                "Cloud Cost Allocation",
                "Cloud FinOps",
                "Documents tag requirements and monthly review process for cloud costs consumed by connected vehicle platforms.",
                ("cloud tag", "cost report", "service owner"),
                ("Cloud Console", "FinOps Dashboard", "ERP"),
            ),
            PageSpec(
                "License Renewal Budget",
                "Finance Business Partner",
                "Explains budget planning for engineering tools such as compilers, static analysis, simulation, and test platforms.",
                ("license owner", "renewal quote", "usage report"),
                ("License Portal", "Procurement Portal", "Finance Approval"),
            ),
            PageSpec(
                "Capital Equipment Request",
                "Finance Business Partner",
                "Defines capital request process for HIL rigs, lab instrumentation, build servers, and vehicle benches.",
                ("capital request", "depreciation class", "business case"),
                ("ERP", "Asset Register", "Procurement Portal"),
            ),
            PageSpec(
                "Project Budget Forecast",
                "Program Finance",
                "Explains monthly forecast inputs for automotive software programs, including labor, tooling, cloud, and supplier costs.",
                ("forecast template", "cost variance", "program baseline"),
                ("ERP", "Planning Tool", "Finance Dashboard"),
            ),
            PageSpec(
                "Purchase Order Change Request",
                "Procurement",
                "Documents how to request amount, date, supplier, or scope changes for active purchase orders.",
                ("change request", "purchase order", "approval reason"),
                ("Procurement Portal", "ERP", "Supplier Portal"),
            ),
            PageSpec(
                "External Training Payment",
                "Learning Finance",
                "Defines payment handling for external courses, certification exams, and instructor-led technical training.",
                ("training approval", "invoice", "attendance proof"),
                ("Learning Platform", "Invoice Portal", "Finance Approval"),
            ),
            PageSpec(
                "Cost Center Mapping",
                "Finance Operations",
                "Lists rules for mapping engineering teams, feature programs, and support activities to the correct cost center.",
                ("cost center", "program code", "team mapping"),
                ("ERP", "HR Portal", "Finance Dashboard"),
            ),
        ),
    ),
    SectionSpec(
        name="Company Benefits",
        page_type="benefits guide",
        audience="employees and HR partners",
        count_rule="Count these pages as benefits pages. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "Health Insurance Enrollment",
                "Benefits Team",
                "Explains health plan enrollment windows, dependent updates, and required proof documents.",
                ("enrollment form", "dependent proof", "coverage start date"),
                ("Benefits Portal", "HR Portal", "Insurance Provider"),
            ),
            PageSpec(
                "Wellness Budget Claim",
                "Benefits Team",
                "Defines eligible wellness expenses and claim evidence for fitness, mental health, and preventive care.",
                ("claim receipt", "wellness category", "annual limit"),
                ("Benefits Portal", "Expense Tool", "HR Portal"),
            ),
            PageSpec(
                "Pension Contribution Setup",
                "Benefits Team",
                "Explains contribution choices, employer matching rules, and payroll timing for pension setup.",
                ("contribution rate", "beneficiary form", "payroll effective date"),
                ("Benefits Portal", "Payroll System", "Pension Provider"),
            ),
            PageSpec(
                "Parental Leave Benefits",
                "Benefits Team",
                "Summarizes parental leave eligibility, notice timing, pay handling, and return-to-work planning.",
                ("leave request", "expected date", "return plan"),
                ("HR Portal", "Payroll System", "Benefits Portal"),
            ),
            PageSpec(
                "Commuter Transportation Support",
                "Benefits Team",
                "Explains commuter reimbursement and parking support for employees traveling to offices, labs, or plants.",
                ("commuter claim", "travel pass", "monthly cap"),
                ("Benefits Portal", "Expense Tool", "HR Portal"),
            ),
            PageSpec(
                "Home Office Equipment Benefit",
                "Benefits Team",
                "Defines home office equipment support for remote or hybrid employees with approved work arrangements.",
                ("equipment claim", "remote work approval", "asset category"),
                ("Benefits Portal", "IT Store", "Expense Tool"),
            ),
            PageSpec(
                "Employee Assistance Program",
                "Benefits Team",
                "Explains confidential assistance resources for mental health, financial advice, and family support.",
                ("support category", "provider contact", "confidentiality note"),
                ("Benefits Portal", "Provider Portal", "HR Portal"),
            ),
            PageSpec(
                "Learning Platform Access",
                "Learning and Development",
                "Describes access to online learning catalogs for automotive software, cloud, safety, and leadership topics.",
                ("learning account", "course catalog", "completion record"),
                ("Learning Platform", "HR Portal", "Identity Provider"),
            ),
            PageSpec(
                "Annual Leave Carryover",
                "Benefits Team",
                "Explains carryover limits, manager approval, and expiration timing for unused annual leave.",
                ("leave balance", "carryover request", "expiry date"),
                ("HR Portal", "Payroll System", "Calendar"),
            ),
            PageSpec(
                "Relocation Support Package",
                "Benefits Team",
                "Summarizes relocation support for employees moving for engineering roles, plant launches, or lab assignments.",
                ("relocation request", "approved location", "benefit cap"),
                ("Benefits Portal", "HR Portal", "Expense Tool"),
            ),
        ),
    ),
    SectionSpec(
        name="IT Support",
        page_type="IT support procedure",
        audience="employees, service desk agents, endpoint engineers",
        count_rule="Count these pages as IT support procedures. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "Laptop Provisioning Standard",
                "Endpoint Engineering",
                "Defines standard laptop build, required software, encryption, and handover checks for engineering users.",
                ("asset tag", "device profile", "handover checklist"),
                ("MDM Portal", "Asset Register", "Service Desk"),
            ),
            PageSpec(
                "VPN Access Recovery",
                "Network Services",
                "Explains how to recover VPN access when certificates, profiles, or MFA enrollment block connectivity.",
                ("VPN profile", "certificate status", "identity verification"),
                ("VPN Gateway", "Identity Provider", "Service Desk"),
            ),
            PageSpec(
                "MFA Device Replacement",
                "Identity Team",
                "Documents identity verification and enrollment steps when an employee replaces a phone or security key.",
                ("identity proof", "old device status", "new MFA method"),
                ("Identity Provider", "Service Desk", "HR Portal"),
            ),
            PageSpec(
                "Email Distribution List Request",
                "Collaboration Services",
                "Defines how teams request distribution lists for programs, release trains, supplier groups, and support rotations.",
                ("list name", "owner", "membership rule"),
                ("Mail Admin Console", "Identity Provider", "Service Desk"),
            ),
            PageSpec(
                "Endpoint Security Exception",
                "Security Operations",
                "Explains how to request temporary endpoint security exceptions for compilers, lab tools, or hardware drivers.",
                ("exception reason", "file hash", "expiry date"),
                ("Endpoint Console", "Security Review", "Service Desk"),
            ),
            PageSpec(
                "Printer and Badge Support",
                "Workplace Services",
                "Documents support flow for office printers, lab badges, site access cards, and visitor badge issues.",
                ("badge ID", "site location", "access group"),
                ("Badge System", "Service Desk", "Facilities Portal"),
            ),
            PageSpec(
                "Network Access for Test Bench",
                "Network Services",
                "Defines network request details for HIL benches, ECU rigs, lab switches, and isolated VLANs.",
                ("bench ID", "VLAN request", "MAC address list"),
                ("Network Portal", "Lab Inventory", "Firewall Console"),
            ),
            PageSpec(
                "Lost Device Response",
                "Security Operations",
                "Explains immediate steps when a laptop, phone, badge, or removable media device is lost.",
                ("device ID", "last known location", "remote wipe status"),
                ("MDM Portal", "Security Incident Queue", "Asset Register"),
            ),
            PageSpec(
                "Software Installation Request",
                "Endpoint Engineering",
                "Defines request and approval flow for engineering software outside the standard workstation image.",
                ("software name", "license owner", "business justification"),
                ("IT Store", "License Portal", "Service Desk"),
            ),
            PageSpec(
                "Account Deactivation Checklist",
                "Identity Team",
                "Lists deactivation steps for employees, contractors, supplier users, and shared accounts.",
                ("account ID", "end date", "system access list"),
                ("Identity Provider", "HR Portal", "Service Desk"),
            ),
        ),
    ),
    SectionSpec(
        name="Troubleshooting",
        page_type="troubleshooting article",
        audience="support engineers, developers, validation engineers",
        count_rule="Count these pages as troubleshooting articles. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "CAN Bus Trace Missing Frames",
                "Diagnostics Engineering",
                "Troubleshoots missing CAN frames during bench or vehicle capture sessions.",
                ("trace file", "bus load reading", "DBC version"),
                ("CAN Analyzer", "Vehicle Log Portal", "Bench Scheduler"),
            ),
            PageSpec(
                "SOMEIP Service Discovery Failure",
                "Middleware Team",
                "Troubleshoots SOME/IP service discovery issues between ECU services and integration test clients.",
                ("service ID", "instance ID", "multicast route"),
                ("vSomeIP", "Wireshark", "Network Portal"),
            ),
            PageSpec(
                "OTA Update Stuck Pending",
                "OTA Operations",
                "Troubleshoots OTA campaign targets that remain pending after assignment.",
                ("campaign ID", "vehicle cohort", "device state"),
                ("OTA Console", "Telemetry Dashboard", "Incident Desk"),
            ),
            PageSpec(
                "Jenkins Build Agent Offline",
                "Build Infrastructure",
                "Troubleshoots Jenkins agents that stop accepting Linux, Android, QNX, or Yocto build jobs.",
                ("agent label", "node status", "recent job ID"),
                ("Jenkins", "Monitoring Dashboard", "Service Desk"),
            ),
            PageSpec(
                "Docker Compose Network Conflict",
                "Developer Platform",
                "Troubleshoots local Docker Compose failures caused by overlapping ports, networks, or stale containers.",
                ("compose file", "port map", "network name"),
                ("Docker Desktop", "Developer CLI", "Service Desk"),
            ),
            PageSpec(
                "Android HMI Emulator Blank Screen",
                "HMI Platform",
                "Troubleshoots Android emulator blank screen issues for embedded HMI validation.",
                ("emulator image", "GPU mode", "ADB log"),
                ("Android Studio", "ADB", "Vehicle Log Portal"),
            ),
            PageSpec(
                "QNX Target SSH Timeout",
                "Embedded Platform",
                "Troubleshoots SSH timeouts when connecting to QNX targets on benches or lab networks.",
                ("target IP", "bench VLAN", "QNX image version"),
                ("QNX Momentics", "Network Portal", "Bench Scheduler"),
            ),
            PageSpec(
                "Certificate Expired in Test Environment",
                "Security Engineering",
                "Troubleshoots expired certificates used by staging services, test benches, and supplier integration endpoints.",
                ("certificate CN", "expiry date", "service owner"),
                ("Secrets Vault", "Kubernetes", "Certificate Monitor"),
            ),
            PageSpec(
                "Vector Database Sync Lag",
                "Data Platform",
                "Troubleshoots delayed indexing or retrieval lag for knowledge, telemetry, or validation data stores.",
                ("collection name", "sync job ID", "lag duration"),
                ("Qdrant", "PostgreSQL", "Sync Worker"),
            ),
            PageSpec(
                "Vehicle Log Upload Failure",
                "Data Platform",
                "Troubleshoots vehicle log upload failures from benches, fleet vehicles, or validation laptops.",
                ("log bundle", "upload session", "network path"),
                ("Vehicle Log Portal", "Object Storage", "VPN Gateway"),
            ),
        ),
    ),
    SectionSpec(
        name="Onboarding",
        page_type="onboarding guide",
        audience="new hires, managers, onboarding buddies",
        count_rule="Count these pages as onboarding guides. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "First Day Engineering Checklist",
                "Engineering Operations",
                "Lists required first-day tasks for new automotive software engineers.",
                ("laptop handover", "account access", "buddy assignment"),
                ("HR Portal", "Service Desk", "Learning Platform"),
            ),
            PageSpec(
                "Developer Workstation Setup",
                "Developer Platform",
                "Explains baseline workstation tools needed before joining an automotive software project.",
                ("tool list", "security baseline", "verification command"),
                ("IT Store", "GitHub Enterprise", "Developer CLI"),
            ),
            PageSpec(
                "Repository Access Orientation",
                "Developer Platform",
                "Explains how new engineers discover repositories, access groups, branch rules, and code owners.",
                ("repository map", "team slug", "code owner file"),
                ("GitHub Enterprise", "Jira", "Requirements Traceability"),
            ),
            PageSpec(
                "Security Training Path",
                "Security Engineering",
                "Lists mandatory security courses for automotive software, supplier data, and production access.",
                ("training module", "completion proof", "renewal cycle"),
                ("Learning Platform", "HR Portal", "Security Portal"),
            ),
            PageSpec(
                "Automotive Domain Primer",
                "Systems Engineering",
                "Introduces common automotive software concepts used by engineering teams.",
                ("domain glossary", "architecture map", "signal examples"),
                ("Requirements Traceability", "Architecture Wiki", "Vehicle Log Portal"),
            ),
            PageSpec(
                "Team Rituals and Cadence",
                "Engineering Operations",
                "Explains recurring ceremonies, planning cycles, release checkpoints, and support handoffs.",
                ("team calendar", "standup notes", "release review"),
                ("Calendar", "Jira", "Confluence"),
            ),
            PageSpec(
                "Code Review Expectations",
                "Developer Platform",
                "Defines code review quality expectations for safety, testability, maintainability, and traceability.",
                ("pull request", "review checklist", "test evidence"),
                ("GitHub Enterprise", "SonarQube", "Jira"),
            ),
            PageSpec(
                "Test Bench Safety Introduction",
                "Validation Operations",
                "Introduces safety rules for ECU benches, HIL rigs, power supplies, and vehicle test areas.",
                ("bench induction", "safety checklist", "reservation record"),
                ("Bench Scheduler", "Lab Inventory", "Safety Portal"),
            ),
            PageSpec(
                "Release Process Overview",
                "Release Management",
                "Explains high-level release flow from feature readiness to deployment and post-release monitoring.",
                ("release train", "approval gate", "monitoring window"),
                ("Jira Release Hub", "Telemetry Dashboard", "Incident Desk"),
            ),
            PageSpec(
                "First Month Milestones",
                "Engineering Operations",
                "Lists expected first-month outcomes for new engineering hires.",
                ("milestone checklist", "manager review", "buddy feedback"),
                ("HR Portal", "Jira", "Learning Platform"),
            ),
        ),
    ),
    SectionSpec(
        name="Projects Setups",
        page_type="project setup record",
        audience="software engineers, project owners, validation engineers",
        count_rule="Each page in this section counts as exactly one project setup record. Use the page title as the project name.",
        pages=(
            PageSpec(
                "AUTOSAR Gateway Simulator Setup",
                "Embedded Platform",
                "Sets up a local AUTOSAR gateway simulator for integration tests and service routing validation.",
                ("simulator repo", "routing config", "test vector set"),
                ("GitHub Enterprise", "vSomeIP", "CAN Analyzer"),
            ),
            PageSpec(
                "CAN LIN Trace Analyzer Setup",
                "Diagnostics Engineering",
                "Sets up the trace analyzer used to decode CAN and LIN captures during ECU validation.",
                ("decoder config", "DBC library", "trace samples"),
                ("CAN Analyzer", "Vehicle Log Portal", "Artifact Registry"),
            ),
            PageSpec(
                "CI CD Release Pipeline Setup",
                "Build Infrastructure",
                "Sets up a CI/CD pipeline for automotive software builds, quality checks, and release artifacts.",
                ("pipeline yaml", "quality gate", "release artifact"),
                ("Jenkins", "GitHub Enterprise", "Artifactory"),
            ),
            PageSpec(
                "C++ Renderer Engine Setup",
                "HMI Platform",
                "Sets up the C++ rendering engine used by embedded HMI prototypes and graphics performance tests.",
                ("renderer repo", "toolchain file", "performance scene"),
                ("GitHub Enterprise", "CMake", "GPU Profiler"),
            ),
            PageSpec(
                "Flutter Embedded HMI Setup",
                "HMI Platform",
                "Sets up Flutter tooling for embedded HMI screens running on Linux or Android target profiles.",
                ("Flutter repo", "target profile", "asset bundle"),
                ("Flutter SDK", "Android Studio", "Artifact Registry"),
            ),
            PageSpec(
                "HIL Bench Controller Setup",
                "Validation Operations",
                "Sets up the HIL bench controller project used to automate ECU power, stimulation, and measurement.",
                ("bench controller repo", "I/O map", "bench reservation"),
                ("Bench Scheduler", "Python", "Lab Inventory"),
            ),
            PageSpec(
                "Internal DevTools CLI Setup",
                "Developer Platform",
                "Sets up the internal command-line tools used for project bootstrap, diagnostics, and environment checks.",
                ("CLI package", "profile config", "doctor report"),
                ("Developer CLI", "Artifactory", "Secrets Vault"),
            ),
            PageSpec(
                "OEM Infotainment Project Setup",
                "Program Engineering",
                "Sets up the infotainment project workspace for OEM-specific HMI, middleware, and integration tasks.",
                ("program repo", "OEM config", "integration checklist"),
                ("GitHub Enterprise", "Jira", "Requirements Traceability"),
            ),
            PageSpec(
                "OEM Supplier Delivery Package Setup",
                "Supplier Integration",
                "Sets up the supplier delivery package workspace for release notes, evidence, and interface artifacts.",
                ("delivery package", "supplier manifest", "evidence folder"),
                ("Supplier Portal", "Artifact Registry", "Requirements Traceability"),
            ),
            PageSpec(
                "OTA Campaign Simulator Setup",
                "OTA Operations",
                "Sets up an OTA campaign simulator for dry-run validation of cohort targeting and update states.",
                ("campaign simulator", "cohort data", "state machine config"),
                ("OTA Console", "Python", "Telemetry Dashboard"),
            ),
            PageSpec(
                "Qt Wayland HMI Tool Setup",
                "HMI Platform",
                "Sets up the Qt Wayland HMI toolchain for cockpit prototypes and target display validation.",
                ("Qt project", "Wayland profile", "display config"),
                ("Qt Creator", "Wayland Compositor", "GitHub Enterprise"),
            ),
            PageSpec(
                "SOME/IP vSomeIP Service Setup",
                "Middleware Team",
                "Sets up a SOME/IP service using vSomeIP for service discovery and integration testing.",
                ("vSomeIP repo", "service config", "network route"),
                ("vSomeIP", "CMake", "Wireshark"),
            ),
            PageSpec(
                "UDS Diagnostics Toolkit Setup",
                "Diagnostics Engineering",
                "Sets up the UDS diagnostics toolkit used for service tests, DTC reads, and routine control validation.",
                ("diagnostics toolkit", "ODX data", "test scripts"),
                ("Python", "CAN Analyzer", "Vehicle Log Portal"),
            ),
            PageSpec(
                "Vehicle Telemetry Ingestion Setup",
                "Data Platform",
                "Sets up telemetry ingestion for validation vehicles, bench streams, and connected vehicle events.",
                ("ingestion service", "schema contract", "sample event set"),
                ("Kafka", "Schema Registry", "Data Lake"),
            ),
            PageSpec(
                "Yocto Embedded Image Setup",
                "Embedded Platform",
                "Sets up a Yocto image workspace for embedded Linux target builds and board support package validation.",
                ("Yocto layers", "BSP manifest", "image recipe"),
                ("Yocto", "BitBake", "Artifact Registry"),
            ),
        ),
    ),
    SectionSpec(
        name="Other",
        page_type="reference page",
        audience="all technical employees",
        count_rule="Count these pages as general references. Do not count them as project setup records.",
        pages=(
            PageSpec(
                "Glossary of Automotive Software Terms",
                "Systems Engineering",
                "Defines commonly used automotive software terms across embedded, cloud, diagnostics, and validation teams.",
                ("term list", "approved definition", "example usage"),
                ("Architecture Wiki", "Requirements Traceability", "Learning Platform"),
            ),
            PageSpec(
                "Architecture Decision Record Template",
                "Architecture Office",
                "Provides a standard structure for documenting technical decisions and rejected alternatives.",
                ("ADR template", "decision owner", "status"),
                ("Architecture Wiki", "GitHub Enterprise", "Jira"),
            ),
            PageSpec(
                "Data Retention Rules for Logs",
                "Data Governance",
                "Summarizes retention rules for vehicle logs, bench logs, telemetry events, and support attachments.",
                ("retention class", "data owner", "deletion rule"),
                ("Data Catalog", "Object Storage", "Vehicle Log Portal"),
            ),
            PageSpec(
                "Meeting Notes Standard",
                "Engineering Operations",
                "Defines the expected format for project, release, incident, and supplier meeting notes.",
                ("decision log", "action item", "owner"),
                ("Confluence", "Jira", "Calendar"),
            ),
            PageSpec(
                "Naming Convention Catalog",
                "Architecture Office",
                "Lists naming rules for repositories, branches, services, feature flags, test benches, and artifacts.",
                ("naming rule", "prefix", "example"),
                ("Architecture Wiki", "GitHub Enterprise", "Artifact Registry"),
            ),
            PageSpec(
                "Vendor Evaluation Checklist",
                "Supplier Integration",
                "Defines evaluation criteria for tools, suppliers, hosted services, and engineering contractors.",
                ("evaluation scorecard", "risk review", "approval decision"),
                ("Procurement Portal", "Security Review", "Legal Intake"),
            ),
            PageSpec(
                "Cybersecurity Evidence Folder Structure",
                "Security Engineering",
                "Defines how cybersecurity evidence is organized for audits, release gates, and supplier reviews.",
                ("evidence folder", "control ID", "review status"),
                ("Requirements Traceability", "Security Portal", "Document Library"),
            ),
            PageSpec(
                "Documentation Review Workflow",
                "Engineering Operations",
                "Explains how technical documents are reviewed, approved, and refreshed.",
                ("review owner", "approval state", "refresh date"),
                ("Confluence", "GitHub Enterprise", "Jira"),
            ),
            PageSpec(
                "Internal Demo Preparation",
                "Product Engineering",
                "Lists preparation steps for internal demos of HMI features, cloud services, diagnostics, and telemetry dashboards.",
                ("demo script", "data set", "fallback plan"),
                ("Demo Environment", "Telemetry Dashboard", "Jira"),
            ),
            PageSpec(
                "Legacy System Ownership Map",
                "Architecture Office",
                "Maps legacy systems to current owners, support contacts, replacement plans, and dependent teams.",
                ("system name", "owner", "replacement path"),
                ("Architecture Wiki", "Service Catalog", "Jira"),
            ),
        ),
    ),
)


SECTION_GUIDANCE = {
    "Project Deployment": (
        "For questions about deployment readiness, rollout, release gates, rollback, or production enablement, use these pages. "
        "If the user asks for projects or project setup inventory, do not use this section as the source of project names."
    ),
    "HR Question": "For employment, access eligibility, leave, travel, interview, contractor, and people-process questions.",
    "Internal Tools": "For questions about tool access, dashboards, developer systems, package registries, and engineering platforms.",
    "Finances": "For purchase, invoice, travel cost, cloud cost, license, and cost-center questions.",
    "Company Benefits": "For employee benefits, enrollment, wellness, leave benefits, and reimbursement support.",
    "IT Support": "For helpdesk procedures, accounts, endpoint issues, network access, MFA, devices, and software requests.",
    "Troubleshooting": "For known symptoms, diagnostics, likely causes, fixes, and verification steps.",
    "Onboarding": "For new-hire orientation, first-month tasks, security training, and engineering expectations.",
    "Projects Setups": (
        "For project setup inventory and setup instructions. Each page title in this section is one project setup name. "
        "Do not invent additional projects from tools, systems, artifacts, or deployment pages."
    ),
    "Other": "For cross-cutting references, standards, templates, naming, and documentation process questions.",
}


HTML_STYLE = """
body {
  font-family: Aptos, Arial, sans-serif;
  color: #1f2933;
  line-height: 1.45;
  max-width: 900px;
  margin: 32px auto;
  padding: 0 24px;
}
h1 { font-size: 28px; margin: 0 0 8px; }
h2 { font-size: 18px; margin-top: 28px; border-bottom: 1px solid #d9e2ec; padding-bottom: 4px; }
p.summary { font-size: 15px; margin-top: 0; color: #334e68; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #bcccdc; padding: 7px 9px; text-align: left; vertical-align: top; }
th { background: #f0f4f8; width: 210px; }
dl { display: grid; grid-template-columns: 180px 1fr; gap: 6px 14px; margin: 12px 0; }
dt { font-weight: 700; color: #334e68; }
dd { margin: 0; }
ul, ol { padding-left: 24px; }
li { margin: 5px 0; }
pre { background: #102a43; color: #f0f4f8; padding: 12px; border-radius: 6px; overflow-x: auto; }
code { font-family: Consolas, "Courier New", monospace; }
.note { background: #fffbea; border-left: 4px solid #f0b429; padding: 10px 12px; }
.muted { color: #52606d; }
""".strip()


def main() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    write_strategy()
    write_manifest()
    for index, section in enumerate(SECTIONS, start=1):
        folder = OUTPUT_DIR / f"{index:02d}_{safe_name(section.name)}"
        folder.mkdir()
        for page_index, page in enumerate(section.pages, start=1):
            path = folder / f"{page_index:02d}_{safe_name(page.title)}.html"
            path.write_text(render_page(section, page, page_index), encoding="utf-8")


def write_strategy() -> None:
    total_pages = sum(len(section.pages) for section in SECTIONS)
    lines = [
        "# OneNote Automotive Software Content Pack",
        "",
        f"Generated pages: {total_pages}",
        "",
        "## Strategy",
        "",
        "1. Create one OneNote section for each folder name, using the section name after the numeric prefix.",
        "2. Create one OneNote page for each HTML file. Use the H1 title as the OneNote page title.",
        "3. Keep one page focused on one real internal topic. Do not merge unrelated processes into one page.",
        "4. Keep page titles clear and specific because the title is the strongest signal during retrieval.",
        "5. Keep commands in code blocks and do not merge multiple commands into one paragraph.",
        "6. Vary the page layout so sections look maintained by different teams while staying clear.",
        "7. For project inventory, only pages in the Projects Setups section should be considered project setup pages.",
        "",
        "## Writing Rules",
        "",
        "- Write like normal internal company documentation.",
        "- Use natural headings and process wording that a real team would maintain.",
        "- Mix paragraphs, tables, short lists, and command blocks instead of making every page a checklist.",
        "- Prefer concrete owner teams, systems, artifacts, and completion checks.",
        "- Avoid repeated filler. Each page should contain details that are unique to that page.",
        "- Keep setup commands as separate lines in code blocks. Project setup pages include Linux and Windows paths where useful.",
        "",
        "## Copy Into OneNote",
        "",
        "Open an HTML file in a browser, select the rendered page content, copy it, and paste it into a new OneNote page.",
        "Do not paste the raw HTML source unless you intentionally want source code visible in OneNote.",
        "",
        "After import, run a OneNote bootstrap reindex so the app sees the new pages:",
        "",
        "```powershell",
        "docker compose run --rm sync-worker python -m sync_worker.jobs.onenote_bootstrap",
        "```",
    ]
    (OUTPUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest() -> None:
    rows = ["section,page_title,document_kind,owner,audience"]
    for section in SECTIONS:
        for page in section.pages:
            rows.append(
                ",".join(
                    csv_cell(value)
                    for value in (
                        section.name,
                        page.title,
                        section.page_type,
                        page.owner,
                        section.audience,
                    )
                )
            )
    (OUTPUT_DIR / "manifest.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def render_page(section: SectionSpec, page: PageSpec, page_index: int) -> str:
    slug = safe_name(page.title).lower().replace("_", "-")
    variant = (page_index + len(section.name)) % 5
    command_block = render_command_block(section, page, slug)
    body = render_variant(section, page, variant, command_block, slug)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{escape(page.title)}</title>
  <style>{HTML_STYLE}</style>
</head>
<body>
  <article>
    <h1>{escape(page.title)}</h1>
    <p class="summary">{escape(page.focus)}</p>
{body}
  </article>
</body>
</html>
"""


def render_variant(section: SectionSpec, page: PageSpec, variant: int, command_block: str, slug: str) -> str:
    section_body = render_section_specific_page(section, page, variant, command_block, slug)
    if section_body is not None:
        return section_body

    if variant == 0:
        parts = [
            paragraph_section("Overview", overview_for(section, page)),
            ownership_table(section, page, "Ownership"),
            list_section("Before You Start", inputs_for(section, page)),
            ordered_section(process_heading_for(section), procedure_for(section, page)),
            command_block,
            list_section("Acceptance Checks", checks_for(section, page)),
            list_section("Risks and Notes", risks_for(section, page)),
            escalation_section(section, page, "Escalation"),
        ]
    elif variant == 1:
        parts = [
            paragraph_section("When This Applies", overview_for(section, page)),
            ownership_definition_list(section, page, "Owner and Systems"),
            list_section("What To Prepare", inputs_for(section, page)),
            ordered_section(process_heading_for(section), procedure_for(section, page)),
            command_block,
            list_section("Done When", checks_for(section, page)),
            paragraph_section("Evidence To Keep", f"Keep {evidence_for(section, page)} with the ticket, request, workspace, or release record."),
            list_section("Watch-outs", risks_for(section, page)),
            escalation_section(section, page, "Contact"),
        ]
    elif variant == 2:
        parts = [
            paragraph_section("Purpose", overview_for(section, page)),
            list_section("Required Material", inputs_for(section, page)),
            command_block,
            ordered_section("Working Flow", procedure_for(section, page)),
            ownership_table(section, page, "Scope and Ownership"),
            list_section("Review Checks", checks_for(section, page)),
            list_section("Known Issues", risks_for(section, page)),
            escalation_section(section, page, "Handoff"),
        ]
    elif variant == 3:
        parts = [
            note_section("Practical Summary", overview_for(section, page)),
            ownership_definition_list(section, page, "Responsibilities"),
            ordered_section(process_heading_for(section), procedure_for(section, page)),
            list_section("Preparation", inputs_for(section, page)),
            command_block,
            list_section("Verification", checks_for(section, page)),
            list_section("Notes", risks_for(section, page)),
            escalation_section(section, page, "Escalate When"),
        ]
    else:
        parts = [
            paragraph_section("Team Note", overview_for(section, page)),
            list_section("Information Needed", inputs_for(section, page)),
            ownership_table(section, page, "People and Systems"),
            command_block,
            ordered_section("How We Handle It", procedure_for(section, page)),
            list_section("Completion Check", checks_for(section, page)),
            paragraph_section("Records", f"The usual records are {evidence_for(section, page)}. Keep them linked where the work is tracked."),
            list_section("Cautions", risks_for(section, page)),
            escalation_section(section, page, "Owner Follow-up"),
        ]
    return "\n\n".join(part for part in parts if part.strip())


def render_section_specific_page(
    section: SectionSpec,
    page: PageSpec,
    variant: int,
    command_block: str,
    slug: str,
) -> str | None:
    if section.name == "Projects Setups":
        return render_project_setup_page(section, page, variant, slug)
    if section.name == "Project Deployment":
        return render_deployment_page(section, page, variant)
    if section.name == "HR Question":
        return render_hr_page(section, page, variant)
    if section.name == "Internal Tools":
        return render_internal_tool_page(section, page, variant)
    if section.name == "Finances":
        return render_finance_page(section, page, variant)
    if section.name == "Company Benefits":
        return render_benefit_page(section, page, variant)
    if section.name == "IT Support":
        return render_it_support_page(section, page, variant)
    if section.name == "Troubleshooting":
        return render_troubleshooting_page(section, page, variant, command_block)
    if section.name == "Onboarding":
        return render_onboarding_page(section, page, variant)
    if section.name == "Other":
        return render_reference_page(section, page, variant)
    return None


def render_project_setup_page(section: SectionSpec, page: PageSpec, variant: int, slug: str) -> str:
    command_blocks = project_command_sections(page, slug, variant)
    if variant in {0, 2}:
        parts = [
            paragraphs_section("Project Context", project_context_paragraphs(page)),
            project_download_section(page, slug),
            ownership_definition_list(section, page, "Who Maintains It"),
            paragraphs_section("Before Opening a Terminal", project_before_terminal(page)),
            command_blocks,
            paragraphs_section("After the First Build", project_after_build(page)),
            list_section("Checks To Keep With The Ticket", checks_for(section, page)),
            list_section("Typical Setup Problems", risks_for(section, page)),
            escalation_section(section, page, "When To Ask For Help"),
        ]
    else:
        parts = [
            paragraphs_section("What This Workspace Is For", project_context_paragraphs(page)),
            ownership_table(section, page, "Team and Systems"),
            project_download_section(page, slug),
            paragraphs_section("Access Notes", project_access_notes(page, slug)),
            command_blocks,
            paragraphs_section("How Engineers Usually Work With It", project_workflow_story(page)),
            list_section("Ready Check", checks_for(section, page)),
            escalation_section(section, page, "Support Path"),
        ]
    return "\n\n".join(part for part in parts if part.strip())


def render_deployment_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Release Context", deployment_story(page)),
        ownership_table(section, page, "Release Ownership"),
        paragraphs_section("How The Release Usually Moves", deployment_flow(page)),
        list_section("Gate Checks", checks_for(section, page)),
        paragraphs_section("Evidence Trail", (f"Keep {evidence_for(section, page)} together with the release ticket. The release owner should be able to open one record and see what was deployed, who approved it, which monitoring view was used, and who owns rollback.",)),
        list_section("Release Risks", risks_for(section, page)),
        escalation_section(section, page, "Escalation"),
    ]
    if variant % 2:
        parts[1], parts[2] = parts[2], parts[1]
    return "\n\n".join(parts)


def render_hr_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Policy Explanation", hr_story(page)),
        paragraphs_section("Employee Path", employee_path(page)),
        ownership_definition_list(section, page, "Policy Owner"),
        list_section("What HR Checks", checks_for(section, page)),
        paragraphs_section("Privacy Note", (f"Keep employee-specific information in {page.systems[0]} or the approved HR case tool. Notes should explain the rule and the expected path, not store private employee details.",)),
        escalation_section(section, page, "Exceptions"),
    ]
    if variant % 2 == 0:
        parts.insert(2, list_section("Useful Inputs", inputs_for(section, page)))
    return "\n\n".join(parts)


def render_internal_tool_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Tool Owner Note", internal_tool_story(page)),
        ownership_definition_list(section, page, "Access Model"),
        paragraphs_section("Request Flow", tool_request_story(page)),
        list_section("Access Review Points", checks_for(section, page)),
        paragraphs_section("Operational Habit", (f"When the tool is used during release or validation work, link the ticket back to {page.artifacts[0]} and keep the owner visible. That makes later audits easier because the access reason, the system, and the responsible team stay together.",)),
        list_section("Things That Usually Go Wrong", risks_for(section, page)),
    ]
    if variant == 3:
        parts[1], parts[2] = parts[2], parts[1]
    return "\n\n".join(parts)


def render_finance_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Finance Note", finance_story(page)),
        ownership_table(section, page, "Approval Owner"),
        paragraphs_section("Approval Route", finance_route(page)),
        paragraphs_section("Record Keeping", (f"The expected record contains {evidence_for(section, page)}. Keep it attached to the purchase, supplier, travel, or cost-center record so engineering and finance do not have to reconstruct the decision later.",)),
        list_section("Finance Checks", checks_for(section, page)),
        list_section("Common Delays", risks_for(section, page)),
    ]
    if variant in {1, 4}:
        parts.insert(2, list_section("What To Bring", inputs_for(section, page)))
    return "\n\n".join(parts)


def render_benefit_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Employee Guide", benefit_story(page)),
        paragraphs_section("How Enrollment Usually Works", benefit_enrollment(page)),
        ownership_definition_list(section, page, "Benefit Owner"),
        paragraphs_section("Important Detail", (f"Eligibility can depend on country, contract type, start date, and enrollment window. The page should point employees to {page.systems[0]} for the actual submission and use {page.systems[1]} or {page.systems[2]} only when the benefit owner asks for it.",)),
        list_section("Completion Checks", checks_for(section, page)),
        escalation_section(section, page, "Questions"),
    ]
    if variant == 0:
        parts.append(list_section("Notes", risks_for(section, page)))
    return "\n\n".join(parts)


def render_it_support_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Service Desk Note", it_support_story(page)),
        ownership_table(section, page, "Support Ownership"),
        paragraphs_section("Triage", support_triage(page)),
        list_section("Ticket Closure Checks", checks_for(section, page)),
        paragraphs_section("Requester Communication", (f"Tell the requester what changed, what still needs their action, and where the ticket is recorded. For this page, the normal systems are {', '.join(page.systems)}.",)),
        list_section("Support Risks", risks_for(section, page)),
    ]
    if variant % 2:
        parts.insert(3, list_section("Details To Collect", inputs_for(section, page)))
    return "\n\n".join(parts)


def render_troubleshooting_page(section: SectionSpec, page: PageSpec, variant: int, command_block: str) -> str:
    parts = [
        paragraphs_section("Field Note", troubleshooting_story(page)),
        paragraphs_section("Before Changing Anything", troubleshooting_before_fix(page)),
        command_block,
        paragraphs_section("Reading The Result", (f"Compare the current output with the last known good state and the affected environment. For this case the important evidence is {', '.join(page.artifacts)}, and the relevant systems are {', '.join(page.systems)}.",)),
        ordered_section("Investigation Path", procedure_for(section, page)),
        list_section("Recovery Check", checks_for(section, page)),
        list_section("Notes From Previous Incidents", risks_for(section, page)),
        escalation_section(section, page, "Escalation"),
    ]
    if variant in {2, 4}:
        parts[1], parts[3] = parts[3], parts[1]
    return "\n\n".join(part for part in parts if part.strip())


def render_onboarding_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Buddy Note", onboarding_story(page)),
        paragraphs_section("First Week Context", onboarding_context(page)),
        ownership_definition_list(section, page, "People Involved"),
        list_section("What Should Be Ready", inputs_for(section, page)),
        paragraphs_section("How To Know It Worked", (f"The useful signal is not only that the page was read. The new hire should have enough access to use {page.systems[0]}, know where {page.systems[1]} fits, and understand when to ask about {page.systems[2]}.",)),
        list_section("Completion", checks_for(section, page)),
        list_section("Onboarding Notes", risks_for(section, page)),
    ]
    if variant == 1:
        parts[2], parts[3] = parts[3], parts[2]
    return "\n\n".join(parts)


def render_reference_page(section: SectionSpec, page: PageSpec, variant: int) -> str:
    parts = [
        paragraphs_section("Reference Note", reference_story(page)),
        ownership_table(section, page, "Maintained By"),
        paragraphs_section("How Teams Use It", reference_usage(page)),
        list_section("Useful Material", inputs_for(section, page)),
        paragraphs_section("Review Habit", (f"When this reference changes, link the decision or review note in {page.systems[0]} and tell the teams that depend on {page.systems[1]}. If the change affects artifacts, also update {page.systems[2]}.",)),
        list_section("Checks", checks_for(section, page)),
    ]
    if variant % 2:
        parts[1], parts[2] = parts[2], parts[1]
    return "\n\n".join(parts)


def paragraph_section(title: str, text: str) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <p>{escape(text)}</p>"""


def paragraphs_section(title: str, paragraphs: tuple[str, ...] | list[str]) -> str:
    body = "\n    ".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
    return f"""    <h2>{escape(title)}</h2>
    {body}"""


def note_section(title: str, text: str) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <p class="note">{escape(text)}</p>"""


def list_section(title: str, items: tuple[str, ...] | list[str]) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <ul>
      {render_list(items)}
    </ul>"""


def ordered_section(title: str, items: tuple[str, ...] | list[str]) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <ol>
      {render_list(items)}
    </ol>"""


def ownership_table(section: SectionSpec, page: PageSpec, title: str) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <table>
      <tr><th>Owner team</th><td>{escape(page.owner)}</td></tr>
      <tr><th>Audience</th><td>{escape(section.audience)}</td></tr>
      <tr><th>Review rhythm</th><td>{escape(review_rhythm_for(section))}</td></tr>
      <tr><th>Primary systems</th><td>{escape(', '.join(page.systems))}</td></tr>
    </table>"""


def ownership_definition_list(section: SectionSpec, page: PageSpec, title: str) -> str:
    return f"""    <h2>{escape(title)}</h2>
    <dl>
      <dt>Owner</dt><dd>{escape(page.owner)}</dd>
      <dt>For</dt><dd>{escape(section.audience)}</dd>
      <dt>Systems</dt><dd>{escape(', '.join(page.systems))}</dd>
      <dt>Review</dt><dd>{escape(review_rhythm_for(section))}</dd>
    </dl>"""


def escalation_section(section: SectionSpec, page: PageSpec, title: str) -> str:
    return paragraph_section(
        title,
        f"Escalate unclear ownership, missing evidence, blocked approvals, or exceptions to {page.owner}. "
        f"The usual requester is the {requester_for(section)}, and the standard service desk or program channel should hold the final note.",
    )


def project_context_paragraphs(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is used when an engineer needs a working local copy of the project, not just read access to the repository. {page_focus_sentence(page)}",
        f"The setup normally starts with access to {page.systems[0]}, then moves through the required artifacts: {', '.join(page.artifacts)}. The important part is to keep the machine, the project configuration, and the verification output aligned. If those three do not match, the project can appear to work locally and still fail during integration.",
        f"{page.owner} keeps this page current because small toolchain changes matter in automotive work. A different compiler, DBC file, ODX package, schema version, or bench profile can change the result enough to waste a full validation session.",
    )


def project_before_terminal(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Confirm that your account is already in the right access group for {page.systems[0]}. Do that before opening a terminal, because clone and package errors often look like network problems when they are actually permission problems.",
        f"Create a clean workspace and avoid reusing an old directory from another vehicle program. Keep {page.artifacts[0]} and {page.artifacts[1]} next to the setup ticket so another engineer can reproduce the same run later.",
    )


def project_access_notes(page: PageSpec, slug: str) -> tuple[str, ...]:
    repo_url = project_repo_url(page, slug)
    return (
        f"The main repository or manifest is available from {repo_url}. The download package is published through https://downloads.company.local/automotive/{slug}/ and the working setup notes live at https://docs.company.local/automotive/{slug}/setup.",
        f"For Windows laptops, use the PowerShell section first and keep long paths enabled in Git. For Linux laptops or WSL, use the shell section. If the project touches lab equipment, check the reservation or bench status before running anything that talks to hardware.",
    )


def project_after_build(page: PageSpec) -> tuple[str, ...]:
    return (
        f"After the first successful build, attach the terminal output and the generated local config to the setup ticket. The expected evidence is {evidence_for_name('Projects Setups')}, plus any project-specific logs created by {page.systems[1]} or {page.systems[2]}.",
        f"Do not clean the workspace until the verification step has passed once. Keeping the first build directory for a day makes it easier for {page.owner} to compare cache files, generated code, downloaded packages, or tool versions if something fails for the next engineer.",
    )


def project_workflow_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Engineers usually start this workspace during onboarding, release preparation, or a supplier handoff. The first run should be treated like a controlled setup: download the project material, install the exact tools, run the verification command, and then save the output.",
        f"Once the project is running, daily work should happen on a feature branch with the same local profile used during setup. If {page.artifacts[2]} changes, repeat the verification command before blaming the application code.",
    )


def project_download_section(page: PageSpec, slug: str) -> str:
    repo_url = project_repo_url(page, slug)
    download_url = f"https://downloads.company.local/automotive/{slug}/"
    docs_url = f"https://docs.company.local/automotive/{slug}/setup"
    windows_url = f"https://downloads.company.local/automotive/{slug}/windows-tools.zip"
    return f"""    <h2>Downloads and Links</h2>
    <p>Use the internal links below rather than files passed through chat. They point to the maintained project material and keep the setup reproducible for release, validation, and supplier support.</p>
    <p><strong>Repository:</strong> <a href="{escape(repo_url)}">{escape(repo_url)}</a></p>
    <p><strong>Download package:</strong> <a href="{escape(download_url)}">{escape(download_url)}</a></p>
    <p><strong>Setup notes:</strong> <a href="{escape(docs_url)}">{escape(docs_url)}</a></p>
    <p><strong>Windows tools bundle:</strong> <a href="{escape(windows_url)}">{escape(windows_url)}</a></p>"""


def project_command_sections(page: PageSpec, slug: str, variant: int) -> str:
    linux_title, linux_language, linux_lines = PROJECT_SETUP_COMMANDS.get(
        page.title,
        (
            "Linux Setup",
            "bash",
            (
                f"mkdir -p ~/automotive/{slug}",
                f"cd ~/automotive/{slug}",
                f"git clone ssh://git.company.local/projects/{slug}.git .",
                "./scripts/bootstrap.sh",
                "./scripts/verify.sh",
            ),
        ),
    )
    config_language, config_body = project_config_example(page, slug)
    blocks = [
        command_section("Windows Setup", "powershell", "\n".join(windows_setup_commands(page, slug)), "Use this path on a company Windows laptop or before switching into WSL."),
        command_section(linux_title, linux_language, "\n".join(linux_lines), "Use this path on Linux, WSL, or a standard validation workstation."),
        command_section("Local Config Example", config_language, config_body, "Keep this file local unless the project owner asks for it in the repository."),
        command_section("Verification Commands", "bash", "\n".join(project_verification_commands(page, slug)), "Run verification after setup and again after changing profiles, schemas, or hardware mappings."),
    ]
    if variant in {1, 3}:
        blocks[0], blocks[1] = blocks[1], blocks[0]
    return "\n\n".join(blocks)


def windows_setup_commands(page: PageSpec, slug: str) -> tuple[str, ...]:
    repo_url = project_repo_url(page, slug)
    base = [
        f"$workspace = Join-Path $env:USERPROFILE \"automotive\\{slug}\"",
        "New-Item -ItemType Directory -Force $workspace | Out-Null",
        "Set-Location $workspace",
        "git config --global core.longpaths true",
    ]
    title = page.title
    if "Yocto" in title:
        return tuple(
            base
            + [
                "wsl --install -d Ubuntu-22.04",
                "wsl bash -lc \"sudo apt update && sudo apt install -y git repo gawk wget diffstat unzip texinfo gcc build-essential chrpath socat cpio python3 python3-pip xz-utils zstd\"",
                f"wsl bash -lc \"mkdir -p ~/automotive/{slug} && cd ~/automotive/{slug} && repo init -u ssh://git.company.local/embedded/yocto-manifest.git -b kirkstone\"",
                f"wsl bash -lc \"cd ~/automotive/{slug} && repo sync -c --jobs=8\"",
            ]
        )
    if "Flutter" in title:
        tools = ["winget install -e --id Git.Git", "winget install -e --id Google.Flutter", "winget install -e --id Google.AndroidStudio"]
    elif "Renderer" in title or "SOME/IP" in title or "Qt" in title:
        tools = ["winget install -e --id Git.Git", "winget install -e --id Kitware.CMake", "winget install -e --id Ninja-build.Ninja", "winget install -e --id WiresharkFoundation.Wireshark"]
    elif "CI CD" in title:
        tools = ["winget install -e --id Git.Git", "winget install -e --id Python.Python.3.12", "winget install -e --id EclipseAdoptium.Temurin.17.JDK"]
    elif "DevTools" in title:
        tools = ["winget install -e --id Python.Python.3.12", "py -3.12 -m pip install --upgrade company-devtools"]
    else:
        tools = ["winget install -e --id Git.Git", "winget install -e --id Python.Python.3.12"]
    clone_step = [] if "DevTools" in title else [f"git clone {repo_url} ."]
    return tuple(base + tools + clone_step + ["Write-Output \"Run the Linux or project-specific verification block after tools are installed.\""])


def project_verification_commands(page: PageSpec, slug: str) -> tuple[str, ...]:
    title = page.title
    if "Flutter" in title:
        return ("flutter doctor", "flutter test", "flutter analyze")
    if "Yocto" in title:
        return ("source poky/oe-init-build-env build-auto", "bitbake company-image-minimal -n", "bitbake company-image-minimal")
    if "Telemetry" in title:
        return ("docker compose ps", "python tools/consume_sample_events.py --limit 5", "pytest tests/integration/test_ingestion_flow.py")
    if "SOME/IP" in title:
        return ("./build/bin/service_smoke_test --config configs/local.json", "tshark -i any -f \"udp port 30490\" -a duration:10")
    if "Renderer" in title or "Qt" in title:
        return ("ctest --test-dir build --output-on-failure", "./build/tools/render_smoke_test --headless")
    if "CAN LIN" in title or "UDS" in title:
        return ("pytest tests -q", "python tools/export_diagnostic_report.py --output reports/setup-check.zip")
    if "HIL" in title:
        return ("python -m hil_controller doctor --bench BENCH-ID", "python -m hil_controller dry-run --profile bench-local")
    return ("pytest tests -q", f"tar -czf {slug}-setup-evidence.tgz logs reports")


def project_config_example(page: PageSpec, slug: str) -> tuple[str, str]:
    title = page.title
    if "SOME/IP" in title:
        return (
            "json",
            """{
  "unicast": "192.168.56.20",
  "logging": { "level": "info", "console": true },
  "applications": [{ "name": "company-someip-service", "id": "0x1340" }],
  "services": [{ "service": "0x1234", "instance": "0x0001", "reliable": 30509, "unreliable": 30510 }],
  "service-discovery": { "enable": true, "multicast": "224.244.224.245", "port": 30490 }
}""",
        )
    if "Flutter" in title:
        return (
            "yaml",
            """target_profile: bench-linux
asset_bundle: cockpit_debug
display:
  width: 1920
  height: 720
  pixel_ratio: 1.0
telemetry_overlay: true""",
        )
    if "Yocto" in title:
        return (
            "bash",
            """MACHINE = "company-qemu-auto"
DISTRO = "company-automotive"
IMAGE_FEATURES += "ssh-server-openssh debug-tweaks"
BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8\"""",
        )
    if "Telemetry" in title:
        return (
            "yaml",
            """kafka:
  bootstrap_servers: kafka.dev.company.local:9092
  topic: vehicle.telemetry.validation
schema:
  subject: vehicle-event-value
  compatibility: BACKWARD
sample_window_minutes: 15""",
        )
    if "CAN LIN" in title:
        return (
            "yaml",
            """decoder:
  dbc_path: data/dbc/powertrain.dbc
  lin_schedule: data/lin/body_control.ldf
capture:
  default_channel: can0
  max_bus_load_percent: 70""",
        )
    return (
        "yaml",
        f"""workspace: ~/automotive/{slug}
owner_team: {page.owner}
primary_artifact: {page.artifacts[0]}
local_profile: automotive-dev
verification_output: reports/setup-check.zip""",
    )


def project_repo_url(page: PageSpec, slug: str) -> str:
    command_spec = PROJECT_SETUP_COMMANDS.get(page.title)
    if command_spec is not None:
        for line in command_spec[2]:
            if "ssh://git.company.local/" in line:
                match = re.search(r"ssh://git\.company\.local/[^ ]+", line)
                if match:
                    return match.group(0)
    return f"ssh://git.company.local/projects/{slug}.git"


def deployment_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is written for the moment when engineering work is almost finished but production risk is still real. {page_focus_sentence(page)}",
        f"The release owner should read it before the deployment window starts, not during the window. The page connects the release material with {page.systems[0]}, {page.systems[1]}, and {page.systems[2]} so the team can see what is moving and how rollback will work.",
    )


def deployment_flow(page: PageSpec) -> tuple[str, ...]:
    return (
        f"The normal path starts with {page.artifacts[0]}, then confirms {page.artifacts[1]}, and finally checks {page.artifacts[2]}. When one of those is missing, the release should stay in preparation rather than becoming a production incident.",
        f"During the window, {page.owner} keeps the handoff short: what changed, what dashboard is watched, who can stop the rollout, and where the final note will be attached.",
    )


def hr_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} should read like an answer from HR to an employee who wants to know what happens next. {page_focus_sentence(page)}",
        f"The page should explain the rule in plain language first, then point to {page.systems[0]} for the actual request. Managers can use it to understand timing and approval responsibility without copying private employee data into shared notes.",
    )


def employee_path(page: PageSpec) -> tuple[str, ...]:
    return (
        f"The employee normally starts with {page.artifacts[0]} and checks whether {page.artifacts[1]} is needed. If the case depends on a date, contract type, country, or release freeze, the manager should ask {page.owner} before promising an exception.",
        f"When the request is complete, the final answer should be recorded in {page.systems[0]} or the approved case system. The shared page stays general so future employees can reuse it.",
    )


def internal_tool_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is maintained for teams that need the tool during software delivery, validation, or support. {page_focus_sentence(page)}",
        f"The important distinction is access level. A developer who only reads data should not receive the same role as a release owner, tool maintainer, or audit reviewer.",
    )


def tool_request_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"The request should name the exact target system, usually {page.systems[0]}, and include {page.artifacts[0]} and {page.artifacts[1]}. If the tool is connected to source code, vehicle data, or supplier evidence, the owner should prefer a group role over one-off manual access.",
        f"After access is granted, the requester should open the tool once and confirm that the expected project, namespace, or dashboard is visible. That small check prevents a support ticket from being closed while the user still cannot do the work.",
    )


def finance_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is a finance reference for engineering work where cost, approval, or supplier timing matters. {page_focus_sentence(page)}",
        f"Treat the page like an approval memo. It should make the business reason, cost center, approver, and evidence clear enough that Finance Operations can understand the request without asking the engineering team to rewrite it.",
    )


def finance_route(page: PageSpec) -> tuple[str, ...]:
    return (
        f"The request usually starts in {page.systems[0]} with {page.artifacts[0]}. The approver checks {page.artifacts[1]}, then the requester attaches {page.artifacts[2]} before the purchase, invoice, or reimbursement is processed.",
        f"If the work is tied to a vehicle program, supplier delivery, or launch support, keep the project reference visible. It helps finance separate one-off team purchases from program cost.",
    )


def benefit_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is written for an employee comparing benefit options or trying to understand an enrollment step. {page_focus_sentence(page)}",
        f"The language should stay practical: what the employee can do, what the company provides, and what needs to happen before a deadline. Detailed personal choices belong in {page.systems[0]}, not in shared documentation.",
    )


def benefit_enrollment(page: PageSpec) -> tuple[str, ...]:
    return (
        f"The usual path starts by checking eligibility, then opening {page.systems[0]} and confirming whether {page.artifacts[0]} or {page.artifacts[1]} is required. Some benefits need manager or HR confirmation, while others are employee self-service.",
        f"When enrollment is complete, the employee should keep the confirmation from {page.systems[1]} or {page.systems[2]}. The shared page should explain the process, not store individual benefit selections.",
    )


def it_support_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is a service desk note for support cases that need a repeatable path. {page_focus_sentence(page)}",
        f"The support agent should identify the requester, affected asset or account, business reason, and urgency before changing anything. This is especially important when the request touches engineering tools, test benches, VPN, MFA, or production-adjacent systems.",
    )


def support_triage(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Start with {page.artifacts[0]} and verify it against {page.systems[0]}. Then check {page.artifacts[1]} and {page.artifacts[2]} so the ticket has enough detail for another agent to continue the work if the first responder is unavailable.",
        f"Once the fix is applied, tell the requester exactly what changed and what they should try next. The ticket should not close until the requester confirms the result or the support window expires.",
    )


def troubleshooting_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is written for the first engineer who sees the failure and has to decide whether to fix, escalate, or collect more evidence. {page_focus_sentence(page)}",
        f"The page deliberately starts with evidence, because a fast change can hide the original failure. Keep the first logs, the affected environment, and the last known good state before restarting services or changing configuration.",
    )


def troubleshooting_before_fix(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Collect {page.artifacts[0]} and {page.artifacts[1]} before applying the fix. If the case depends on {page.artifacts[2]}, save the version or checksum as part of the incident note.",
        f"Only after that should the engineer touch {page.systems[0]}, {page.systems[1]}, or {page.systems[2]}. The goal is to make recovery possible without losing the reason the issue happened.",
    )


def onboarding_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is meant to be used by a new hire and a buddy sitting together, not by someone silently checking boxes. {page_focus_sentence(page)}",
        f"The buddy should explain where this fits in daily engineering work and should leave enough room for questions. A person can finish the form and still be blocked if they do not know which system to open first on Monday morning.",
    )


def onboarding_context(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Start with {page.artifacts[0]}, then make sure {page.artifacts[1]} and {page.artifacts[2]} are not only assigned but usable. If a tool asks for extra approval, open the service desk ticket while the new hire is still in the onboarding session.",
        f"The page should be updated when the team changes tools, review habits, safety rules, or release cadence. Old onboarding pages create slow first weeks because people follow steps that no longer match the team.",
    )


def reference_story(page: PageSpec) -> tuple[str, ...]:
    return (
        f"{page.title} is a shared reference for teams that need the same wording, decision, or convention. {page_focus_sentence(page)}",
        f"It should be short enough to stay readable but specific enough that two teams do not interpret the same term or rule differently. The owner should keep examples current because examples are usually what people copy.",
    )


def reference_usage(page: PageSpec) -> tuple[str, ...]:
    return (
        f"Teams usually open this page while preparing a review, naming something new, writing a decision record, or checking an audit detail. The useful material is {', '.join(page.artifacts)}.",
        f"When the reference affects repositories, artifacts, or architecture records, update {page.systems[0]}, {page.systems[1]}, and {page.systems[2]} in the same change window.",
    )


def evidence_for_name(section_name: str) -> str:
    if section_name == "Projects Setups":
        return "setup ticket, access approval, bootstrap output, verification log"
    return "owner confirmation, review date, linked decision or reference artifact"


def procedure_for(section: SectionSpec, page: PageSpec) -> tuple[str, ...]:
    if section.name == "Projects Setups":
        return (
            f"Create the workspace and request access to {page.systems[0]} before pulling project material.",
            f"Check that the assigned engineering group has access to {page.systems[1]} and {page.systems[2]}.",
            f"Collect the required artifacts: {', '.join(page.artifacts)}.",
            "Run bootstrap and verification commands from a clean workspace.",
            "Attach the verification output to the onboarding or project setup ticket.",
        )
    if section.name == "Troubleshooting":
        return (
            "Capture the current error, timestamp, affected environment, and owner before changing configuration.",
            f"Collect diagnostic inputs: {', '.join(page.artifacts)}.",
            f"Check the relevant systems in this order: {', '.join(page.systems)}.",
            "Apply the documented fix only after preserving logs and current configuration.",
            "Verify that the symptom is gone and attach the before-and-after evidence.",
        )
    if section.name == "Project Deployment":
        return (
            "Confirm the release scope, affected environment, and planned deployment window.",
            f"Review the required artifacts: {', '.join(page.artifacts)}.",
            "Check that approvals, release gates, and monitoring owners are recorded.",
            f"Coordinate the handoff through {page.owner}.",
            "Do not proceed to production until the release owner has signed off.",
        )
    if section.name in {"HR Question", "Company Benefits"}:
        return (
            "Check the employee situation, eligibility window, and required documents.",
            "Confirm the policy version and effective date before giving an answer.",
            f"Use {page.systems[0]} as the first source of action or submission.",
            f"Escalate exceptions to {page.owner}.",
            "Provide the answer without exposing personal employee data.",
        )
    if section.name == "Finances":
        return (
            "Check whether the request is operational expense, capital expense, license cost, or travel cost.",
            f"Collect the required artifacts: {', '.join(page.artifacts)}.",
            "Verify cost center, approver, and supporting evidence before submission.",
            f"Submit through {page.systems[0]} and track status until approved or rejected.",
            "Attach approval evidence to the project or purchase record.",
        )
    if section.name == "IT Support":
        return (
            "Verify requester identity and business need before changing accounts, devices, or network access.",
            f"Collect the required support fields: {', '.join(page.artifacts)}.",
            f"Open or update the service ticket in {page.systems[-1]}.",
            "Apply the approved change and record exactly what was changed.",
            "Close the ticket only after the requester confirms resolution.",
        )
    if section.name == "Internal Tools":
        return (
            "Identify the tool owner, target role, and required access level.",
            f"Collect tool-specific inputs: {', '.join(page.artifacts)}.",
            f"Submit access or configuration through {page.systems[0]}.",
            "Verify least-privilege access and document the owner.",
            "Review access quarterly or when the employee changes role.",
        )
    if section.name == "Onboarding":
        return (
            "Confirm the new hire, manager, buddy, start date, and target engineering team.",
            f"Prepare the required items before the session: {', '.join(page.artifacts)}.",
            f"Walk through the related systems with the new hire: {', '.join(page.systems)}.",
            "Record any missing access or training as a service desk ticket.",
            "Ask the manager or buddy to confirm that the onboarding step is complete.",
        )
    return (
        "Check the current owner and review date before relying on the reference.",
        f"Review the supporting material: {', '.join(page.artifacts)}.",
        "Confirm whether the page contains a current rule, template, glossary item, or ownership mapping.",
        f"Ask {page.owner} to update the page if the answer is incomplete.",
        "Link any decision, exception, or change request back to the reference owner.",
    )


def checks_for(section: SectionSpec, page: PageSpec) -> tuple[str, ...]:
    if section.name == "Projects Setups":
        return (
            f"Workspace for {page.title} builds or starts without missing dependencies.",
            f"Access to {', '.join(page.systems)} is confirmed.",
            f"Required artifacts are present: {', '.join(page.artifacts)}.",
            "Setup ticket contains bootstrap output and final verification result.",
        )
    if section.name == "Troubleshooting":
        return (
            "The original symptom is documented with timestamp and environment.",
            f"Diagnostic evidence includes {', '.join(page.artifacts)}.",
            "The fix is linked to a ticket or incident record.",
            "Verification evidence shows the symptom is resolved.",
        )
    if section.name == "Project Deployment":
        return (
            "Release scope, deployment window, and responsible owner are recorded.",
            f"Deployment evidence includes {', '.join(page.artifacts)}.",
            "Rollback owner and monitoring path are known before rollout.",
            "Post-deployment checks are complete before handoff.",
        )
    if section.name == "Onboarding":
        return (
            "The new hire has the required access, equipment, and owner contacts.",
            f"Onboarding evidence includes {', '.join(page.artifacts)}.",
            f"The related systems are available: {', '.join(page.systems)}.",
            "The manager or buddy confirms the onboarding step is complete.",
        )
    return (
        f"Owner team is {page.owner} and has accepted the request or review.",
        f"Required artifacts are available: {', '.join(page.artifacts)}.",
        f"Relevant systems are checked: {', '.join(page.systems)}.",
        "The final decision or completion note is attached to the ticket, request, or record.",
    )


def evidence_for(section: SectionSpec, page: PageSpec) -> str:
    if section.name == "Projects Setups":
        return "setup ticket, access approval, bootstrap output, verification log"
    if section.name == "Troubleshooting":
        return "symptom log, diagnostic output, fix note, verification result"
    if section.name == "Project Deployment":
        return "release approval, validation evidence, monitoring plan, rollback owner"
    if section.name == "Finances":
        return "approval record, cost center, receipt or quote, purchase or invoice ID"
    if section.name in {"HR Question", "Company Benefits"}:
        return "policy source, eligibility rule, request form, approval or enrollment record"
    if section.name == "IT Support":
        return "ticket ID, requester identity, device or account ID, resolution note"
    if section.name == "Internal Tools":
        return "access ticket, tool owner approval, role mapping, audit note"
    if section.name == "Onboarding":
        return "completion checklist, manager confirmation, training record"
    return "owner confirmation, review date, linked decision or reference artifact"


def completion_signal_for(section: SectionSpec, page: PageSpec) -> str:
    if section.name == "Projects Setups":
        return f"{page.artifacts[0]} is available and the verification command completes successfully."
    if section.name == "Troubleshooting":
        return "The original symptom cannot be reproduced and evidence is attached."
    if section.name == "Project Deployment":
        return "Release owner signs off and monitoring shows no blocking regression."
    if section.name == "Finances":
        return "Finance approval is recorded and the request has a traceable reference ID."
    if section.name in {"HR Question", "Company Benefits"}:
        return "Employee receives a clear answer and any required request is submitted."
    if section.name == "IT Support":
        return "Requester confirms the account, device, network, or software issue is resolved."
    if section.name == "Internal Tools":
        return "The user can access the tool with the approved role and no excess permissions."
    if section.name == "Onboarding":
        return "New hire completes the task and manager or buddy confirms readiness."
    return "The reference is reviewed, current, and linked from the relevant team workspace."


def requester_for(section: SectionSpec) -> str:
    return {
        "Project Deployment": "release owner or program lead",
        "HR Question": "employee or manager",
        "Internal Tools": "engineer or team lead",
        "Finances": "project owner or engineering manager",
        "Company Benefits": "employee",
        "IT Support": "employee or service desk agent",
        "Troubleshooting": "support engineer or developer",
        "Onboarding": "new hire or onboarding buddy",
        "Projects Setups": "engineer joining the project",
        "Other": "technical employee or document owner",
    }[section.name]


def overview_for(section: SectionSpec, page: PageSpec) -> str:
    if section.name == "Projects Setups":
        return (
            f"{page.title} is an internal setup guide for engineers joining or maintaining this automotive software workspace. "
            f"{page_focus_sentence(page)} "
            f"It keeps access, artifacts, and verification steps in one place so setup work is repeatable."
        )
    if section.name == "Project Deployment":
        return (
            f"{page.title} is used during release planning and production rollout. "
            f"{page_focus_sentence(page)} "
            "The page should be reviewed before deployment approvals are requested."
        )
    if section.name == "Troubleshooting":
        return (
            f"{page.title} is a support article for recurring technical failures in automotive software environments. "
            f"{page_focus_sentence(page)} "
            "The goal is to preserve evidence, apply the right fix, and verify recovery without guessing."
        )
    if section.name == "Onboarding":
        return (
            f"{page.title} helps a new employee become productive in an automotive software team. "
            f"{page_focus_sentence(page)} "
            "Managers and onboarding buddies should keep this page aligned with the current team process."
        )
    return (
        f"{page.title} is maintained by {page.owner}. "
        f"{page_focus_sentence(page)} "
        "The owner team keeps the required inputs, decisions, and follow-up checks here."
    )


def page_focus_sentence(page: PageSpec) -> str:
    return f"This page {page.focus[:1].lower() + page.focus[1:]}"


def review_rhythm_for(section: SectionSpec) -> str:
    if section.name in {"Project Deployment", "Projects Setups", "Troubleshooting"}:
        return "Review after each major release or tooling change."
    if section.name in {"HR Question", "Company Benefits", "Finances"}:
        return "Review quarterly and after policy or vendor changes."
    if section.name in {"IT Support", "Internal Tools"}:
        return "Review when access rules, tooling, or ownership changes."
    return "Review quarterly or when the owner team changes process."


def inputs_for(section: SectionSpec, page: PageSpec) -> tuple[str, ...]:
    items = [
        f"{sentence_start(page.artifacts[0])} maintained by {page.owner}.",
        f"{sentence_start(page.artifacts[1])} available before work starts.",
        f"{sentence_start(page.artifacts[2])} linked from the ticket, request, or workspace.",
    ]
    if section.name == "Projects Setups":
        items.append(f"Access to {page.systems[0]}, {page.systems[1]}, and {page.systems[2]}.")
    elif section.name == "Project Deployment":
        items.append("Release scope, deployment window, monitoring owner, and rollback owner.")
    elif section.name == "Troubleshooting":
        items.append("Timestamped logs, affected environment, last known good state, and reproduction notes.")
    elif section.name in {"HR Question", "Company Benefits"}:
        items.append("Employee eligibility, request date, manager approval when required, and policy source.")
    elif section.name == "Finances":
        items.append("Cost center, approver, quote or receipt, and expected delivery or service period.")
    elif section.name == "IT Support":
        items.append("Requester identity, asset or account ID, business reason, and expected resolution date.")
    elif section.name == "Internal Tools":
        items.append("Target role, team membership, tool owner approval, and least-privilege access level.")
    elif section.name == "Onboarding":
        items.append("Manager, buddy, start date, team assignment, and required training dates.")
    else:
        items.append("Current owner, review date, linked decision, and affected teams.")
    return tuple(items)


def sentence_start(value: str) -> str:
    return value[:1].upper() + value[1:]


def process_heading_for(section: SectionSpec) -> str:
    if section.name == "Projects Setups":
        return "Setup Process"
    if section.name == "Troubleshooting":
        return "Investigation Process"
    if section.name == "Project Deployment":
        return "Deployment Process"
    if section.name in {"HR Question", "Company Benefits"}:
        return "Employee Process"
    if section.name == "Finances":
        return "Approval Process"
    if section.name == "IT Support":
        return "Support Process"
    if section.name == "Onboarding":
        return "Onboarding Process"
    return "Working Process"


def risks_for(section: SectionSpec, page: PageSpec) -> tuple[str, ...]:
    if section.name == "Projects Setups":
        return (
            "Outdated bootstrap commands can create inconsistent local environments.",
            f"Missing {page.artifacts[1]} usually causes setup to pass locally but fail in integration.",
            "Access should be removed when the engineer leaves the project or supplier engagement.",
        )
    if section.name == "Project Deployment":
        return (
            "Deployment without rollback ownership increases recovery time.",
            "Release evidence must be current for the exact software package being deployed.",
            "Monitoring gaps should block rollout until ownership is clear.",
        )
    if section.name == "Troubleshooting":
        return (
            "Changing configuration before collecting logs can hide the original failure.",
            "A fix applied to the wrong environment can create misleading verification results.",
            "Recurring incidents should be linked to problem management, not closed as one-off tickets.",
        )
    if section.name in {"HR Question", "Company Benefits"}:
        return (
            "Employee-specific details should stay in approved HR systems, not copied into public notes.",
            "Policy exceptions require owner approval before they are communicated as guidance.",
            "Eligibility can depend on country, contract type, or effective date.",
        )
    if section.name == "Finances":
        return (
            "Work should not begin on supplier or purchase activity before approval is recorded.",
            "Wrong cost center mapping can delay invoice handling and reporting.",
            "Quotes, receipts, and approval notes should stay attached to the finance record.",
        )
    if section.name == "IT Support":
        return (
            "Identity verification is required before access, MFA, or device state changes.",
            "Temporary exceptions need expiry dates and owners.",
            "Tickets should not be closed until the requester confirms the fix.",
        )
    if section.name == "Internal Tools":
        return (
            "Tool access should follow least privilege and be reviewed when roles change.",
            "Shared accounts should be avoided unless explicitly approved.",
            "Tool owners are responsible for stale access cleanup.",
        )
    if section.name == "Onboarding":
        return (
            "Missing first-week access slows down training and code review participation.",
            "Safety and security training should be completed before bench or production access is granted.",
            "Managers should update the page when team-specific onboarding changes.",
        )
    return (
        "References should be reviewed before major releases or audits.",
        "Decisions should link to source evidence rather than informal chat messages.",
        "Owner changes should be reflected in the page before teams rely on it.",
    )


PROJECT_SETUP_COMMANDS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "AUTOSAR Gateway Simulator Setup": (
        "Simulator Bootstrap",
        "bash",
        (
            "mkdir -p ~/automotive/autosar-gateway-sim",
            "cd ~/automotive/autosar-gateway-sim",
            "git clone ssh://git.company.local/embedded/autosar-gateway-sim.git .",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements-dev.txt",
            "cp configs/routing.local.example.yaml configs/routing.local.yaml",
            "pytest tests/integration/test_service_routing.py",
        ),
    ),
    "CAN LIN Trace Analyzer Setup": (
        "Analyzer Setup",
        "bash",
        (
            "mkdir -p ~/automotive/can-lin-trace-analyzer",
            "cd ~/automotive/can-lin-trace-analyzer",
            "git clone ssh://git.company.local/diagnostics/can-lin-trace-analyzer.git .",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -e \".[dev]\"",
            "python tools/import_dbc.py data/dbc/powertrain.dbc",
            "pytest tests/test_trace_decoder.py",
        ),
    ),
    "CI CD Release Pipeline Setup": (
        "Pipeline Validation",
        "bash",
        (
            "mkdir -p ~/automotive/ci-release-pipeline",
            "cd ~/automotive/ci-release-pipeline",
            "git clone ssh://git.company.local/build/ci-release-pipeline.git .",
            "cp ci/env.example ci/env.local",
            "yamllint .github/workflows ci/jobs",
            "jenkins-jobs test ci/jobs/release-build.yaml",
            "pytest tests/pipeline_contract",
        ),
    ),
    "C++ Renderer Engine Setup": (
        "Renderer Build",
        "bash",
        (
            "mkdir -p ~/automotive/hmi-renderer",
            "cd ~/automotive/hmi-renderer",
            "git clone ssh://git.company.local/hmi/cpp-renderer-engine.git .",
            "cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DENABLE_WAYLAND=ON",
            "cmake --build build --target renderer_demo --parallel",
            "ctest --test-dir build --output-on-failure",
            "./build/tools/render_smoke_test --scene scenes/performance/basic.scene",
        ),
    ),
    "Flutter Embedded HMI Setup": (
        "Flutter Target Setup",
        "bash",
        (
            "mkdir -p ~/automotive/flutter-embedded-hmi",
            "cd ~/automotive/flutter-embedded-hmi",
            "git clone ssh://git.company.local/hmi/flutter-embedded-hmi.git .",
            "flutter config --enable-linux-desktop",
            "flutter pub get",
            "flutter test",
            "flutter build linux --debug --dart-define=TARGET_PROFILE=bench",
        ),
    ),
    "HIL Bench Controller Setup": (
        "Bench Controller Setup",
        "bash",
        (
            "mkdir -p ~/automotive/hil-bench-controller",
            "cd ~/automotive/hil-bench-controller",
            "git clone ssh://git.company.local/validation/hil-bench-controller.git .",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements-hil.txt",
            "cp benches/example.io-map.yaml benches/local.io-map.yaml",
            "python -m hil_controller doctor --bench BENCH-ID",
        ),
    ),
    "Internal DevTools CLI Setup": (
        "CLI Install",
        "bash",
        (
            "python -m pip install --upgrade company-devtools",
            "company-devtools profile create automotive-dev --region eu",
            "company-devtools auth login",
            "company-devtools doctor --include secrets,artifacts,git",
            "company-devtools bootstrap --workspace ~/automotive/devtools-check",
        ),
    ),
    "OEM Infotainment Project Setup": (
        "Program Workspace",
        "bash",
        (
            "mkdir -p ~/automotive/oem-infotainment",
            "cd ~/automotive/oem-infotainment",
            "repo init -u ssh://git.company.local/oem/infotainment-manifest.git -b main",
            "repo sync -c --jobs=8",
            "python tools/apply_oem_profile.py --profile cockpit-eu",
            "./gradlew :integration:assembleDebug",
            "./gradlew :integration:test",
        ),
    ),
    "OEM Supplier Delivery Package Setup": (
        "Delivery Package",
        "bash",
        (
            "mkdir -p ~/automotive/supplier-delivery-package",
            "cd ~/automotive/supplier-delivery-package",
            "git clone ssh://git.company.local/supplier/delivery-package-template.git .",
            "python tools/create_package.py --release RELEASE-ID --supplier SUPPLIER-ID",
            "python tools/validate_manifest.py delivery/manifest.yaml",
            "zip -r delivery-package.zip delivery evidence release-notes.md",
        ),
    ),
    "OTA Campaign Simulator Setup": (
        "OTA Simulator",
        "bash",
        (
            "mkdir -p ~/automotive/ota-campaign-simulator",
            "cd ~/automotive/ota-campaign-simulator",
            "git clone ssh://git.company.local/ota/campaign-simulator.git .",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements.txt",
            "python simulator/load_cohort.py data/cohorts/bench-vehicles.csv",
            "python simulator/run_campaign.py configs/dry-run.yaml",
        ),
    ),
    "Qt Wayland HMI Tool Setup": (
        "Qt Toolchain",
        "bash",
        (
            "mkdir -p ~/automotive/qt-wayland-hmi-tool",
            "cd ~/automotive/qt-wayland-hmi-tool",
            "git clone ssh://git.company.local/hmi/qt-wayland-hmi-tool.git .",
            "cmake -S . -B build -DCMAKE_PREFIX_PATH=\"$QT_HOME\" -DENABLE_WAYLAND=ON",
            "cmake --build build --target hmi_shell --parallel",
            "WAYLAND_DISPLAY=wayland-1 ./build/bin/hmi_shell --profile cockpit-bench",
        ),
    ),
    "SOME/IP vSomeIP Service Setup": (
        "vSomeIP Service Build",
        "bash",
        (
            "mkdir -p ~/automotive/someip-vsomeip-service",
            "cd ~/automotive/someip-vsomeip-service",
            "git clone ssh://git.company.local/middleware/someip-vsomeip-service.git .",
            "cmake -S third_party/vsomeip -B build/vsomeip -DCMAKE_BUILD_TYPE=Release",
            "cmake --build build/vsomeip --parallel",
            "cmake -S . -B build -DVSOMEIP_ROOT=$PWD/build/vsomeip",
            "cmake --build build --target service_smoke_test --parallel",
            "./build/bin/service_smoke_test --config configs/local.json",
        ),
    ),
    "UDS Diagnostics Toolkit Setup": (
        "Diagnostics Toolkit",
        "bash",
        (
            "mkdir -p ~/automotive/uds-diagnostics-toolkit",
            "cd ~/automotive/uds-diagnostics-toolkit",
            "git clone ssh://git.company.local/diagnostics/uds-toolkit.git .",
            "python -m venv .venv",
            "source .venv/bin/activate",
            "pip install -r requirements-dev.txt",
            "python tools/load_odx.py data/odx/sample_vehicle.odx",
            "pytest tests/test_dtc_read.py tests/test_routine_control.py",
        ),
    ),
    "Vehicle Telemetry Ingestion Setup": (
        "Telemetry Ingestion",
        "bash",
        (
            "mkdir -p ~/automotive/vehicle-telemetry-ingestion",
            "cd ~/automotive/vehicle-telemetry-ingestion",
            "git clone ssh://git.company.local/data/vehicle-telemetry-ingestion.git .",
            "docker compose up -d kafka schema-registry",
            "python tools/register_schema.py schemas/vehicle_event.avsc",
            "python tools/publish_sample_events.py samples/bench-events.jsonl",
            "pytest tests/integration/test_ingestion_flow.py",
        ),
    ),
    "Yocto Embedded Image Setup": (
        "Yocto Image Build",
        "bash",
        (
            "mkdir -p ~/automotive/yocto-embedded-image",
            "cd ~/automotive/yocto-embedded-image",
            "repo init -u ssh://git.company.local/embedded/yocto-manifest.git -b kirkstone",
            "repo sync -c --jobs=8",
            "source poky/oe-init-build-env build-auto",
            "bitbake-layers add-layer ../meta-company-automotive",
            "bitbake company-image-minimal",
        ),
    ),
}


def render_command_block(section: SectionSpec, page: PageSpec, slug: str) -> str:
    if section.name == "Projects Setups":
        command_spec = PROJECT_SETUP_COMMANDS.get(page.title)
        if command_spec is not None:
            title, language, lines = command_spec
            return command_section(title, language, "\n".join(lines))
        body = "\n".join(
            [
                f"mkdir -p ~/automotive/{slug}",
                f"cd ~/automotive/{slug}",
                f"git clone ssh://git.company.local/projects/{slug}.git .",
                "./scripts/bootstrap.sh",
                "./scripts/verify.sh",
            ]
        )
        return command_section("Project Commands", "bash", body)
    if section.name == "Troubleshooting":
        body = "\n".join(
            [
                "# Capture evidence before changing configuration",
                "systemctl status \"$SERVICE_NAME\" --no-pager",
                "journalctl -u \"$SERVICE_NAME\" --since \"30 minutes ago\" --no-pager",
                "ip addr show",
                "ip route",
            ]
        )
        return command_section("Diagnostic Commands", "bash", body)
    return ""


def command_section(
    title: str,
    language: str,
    body: str,
    note: str = "Run commands from a clean shell and keep the output with the related ticket or workspace.",
) -> str:
    return f"""
    <h2>{escape(title)}</h2>
    <p class="note">{escape(note)}</p>
    <pre><code class="language-{escape(language)}">{escape(body)}</code></pre>
"""


def related_keywords(section: SectionSpec, page: PageSpec) -> tuple[str, ...]:
    tokens = [
        section.name,
        section.page_type,
        page.owner,
        *page.artifacts,
        *page.systems,
    ]
    if section.name == "Projects Setups":
        tokens.extend(("project setup", "project inventory", "setup guide"))
    return tuple(dict.fromkeys(tokens))


def render_list(items: tuple[str, ...] | list[str]) -> str:
    return "\n      ".join(f"<li>{escape(item)}</li>" for item in items)


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return normalized or "page"


def csv_cell(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


if __name__ == "__main__":
    main()
