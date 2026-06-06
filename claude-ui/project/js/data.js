/* ============================================================
   Sample content — "Atlas", the knowledge assistant for Vantor
   (a fictional ~2,400-person logistics & robotics company)
   ============================================================ */

const ME = {
  name: "Priya Nair", role: "People Operations", init: "PN",
  email: "priya.nair@vantor.com", dept: "People & HR", since: "Mar 2023",
};

/* roles a user can hold — drives the role-aware greeting & starters */
const ROLES = [
  "People Operations", "Finance", "Engineering",
  "IT & Security", "Product", "Sales", "Facilities",
];

/* departments for the access-request form */
const DEPTS = ["People & HR", "Finance", "Engineering", "IT & Security", "Product", "Sales", "Operations", "Legal"];

/* ---------- OneNote hierarchy: Notebook → Section → Page ---------- */
const NOTEBOOKS = [
  { id: "nb-hr", name: "People & HR", icon: "user", pages: 612, sections: [
    { name: "Benefits", pages: [
      { id: "pg-parental", src: "S1", title: "Parental Leave (US)", edited: "12w" },
      { id: "pg-health",   title: "Health & Dental Plans", edited: "5w" },
      { id: "pg-401k",     title: "401(k) & Match", edited: "9w" },
      { id: "pg-pto",      src: "S8", title: "PTO Policy 2026", edited: "3w" },
    ]},
    { name: "Leave & Absence", pages: [
      { id: "pg-file",  src: "S2", title: "Filing a Leave Claim in Workday", edited: "8w" },
      { id: "pg-loa",   src: "S3", title: "Leave of Absence — Coordination", edited: "6w" },
    ]},
    { name: "Hiring", pages: [
      { id: "pg-loop",  title: "Interview Loop & Scorecards", edited: "2w" },
      { id: "pg-offer", title: "Offer Approvals & Storage", edited: "4w" },
      { id: "pg-ref",   title: "Referral Bonus Program", edited: "16w" },
    ]},
  ]},
  { id: "nb-fin", name: "Finance", icon: "coins", pages: 488, sections: [
    { name: "Expenses & Travel", pages: [
      { id: "pg-exp",  src: "S4", title: "Expense Policy — Meals & Entertainment", edited: "3d" },
      { id: "pg-card", src: "S5", title: "Corporate Card Guidelines", edited: "7w" },
      { id: "pg-trav", title: "Travel Booking & Per Diems", edited: "5w" },
    ]},
    { name: "Procurement", pages: [
      { id: "pg-po",   title: "PO Thresholds & Approvals", edited: "11w" },
      { id: "pg-vend", title: "Vendor Onboarding", edited: "14w" },
    ]},
    { name: "Payroll", pages: [
      { id: "pg-pay",  title: "Pay Schedule & Cutoffs", edited: "2w" },
      { id: "pg-rsu",  title: "Equity & RSU Vesting", edited: "10w" },
    ]},
  ]},
  { id: "nb-eng", name: "Engineering", icon: "code", pages: 734, sections: [
    { name: "Platform", pages: [
      { id: "pg-deploy", title: "Deployment Runbook", edited: "1w" },
      { id: "pg-oncall", src: "S7", title: "On-call & Break-glass Access", edited: "6d" },
      { id: "pg-inc",    title: "Incident Response Process", edited: "3w" },
    ]},
    { name: "Standards", pages: [
      { id: "pg-cr",   title: "Code Review Standards", edited: "8w" },
      { id: "pg-cat",  title: "Service Catalog", edited: "4w" },
    ]},
  ]},
  { id: "nb-sec", name: "IT & Security", icon: "shield", pages: 301, sections: [
    { name: "Access", pages: [
      { id: "pg-prod", src: "S6", title: "Production Access Requests", edited: "5w" },
      { id: "pg-sso",  title: "SSO & MFA Enrollment", edited: "9w" },
    ]},
    { name: "Secrets", pages: [
      { id: "pg-vault", title: "Secrets Management (Vault)", edited: "7w" },
    ]},
  ]},
  { id: "nb-proj", name: "Projects", icon: "box", pages: 156, sections: [
    { name: "Project Atlas", pages: [
      { id: "pg-char", title: "Charter & Objectives", edited: "3w" },
      { id: "pg-mile", title: "Milestones & Status", edited: "4d" },
    ]},
  ]},
  { id: "nb-helios", name: "Project Helios", icon: "lock", pages: 47, restricted: true,
    owner: "M&A Working Group", sections: [] },
  { id: "nb-exec", name: "Exec / Board", icon: "lock", pages: 89, restricted: true,
    owner: "Executive Office", sections: [] },
];

/* ---------- Auto-clustered topics ---------- */
const TOPICS = [
  { id: "t-hr",   name: "HR & People",     color: "oklch(0.70 0.13 25)",  count: 612, icon: "user",   desc: "Benefits, leave, hiring" },
  { id: "t-fin",  name: "Finance",         color: "oklch(0.74 0.12 85)",  count: 488, icon: "coins",  desc: "Expenses, payroll, procurement" },
  { id: "t-eng",  name: "Engineering",     color: "oklch(0.70 0.12 155)", count: 734, icon: "code",   desc: "Deploys, on-call, standards" },
  { id: "t-sec",  name: "IT & Security",   color: "oklch(0.68 0.12 250)", count: 301, icon: "shield", desc: "Access, secrets, devices" },
  { id: "t-proj", name: "Projects",        color: "oklch(0.66 0.13 305)", count: 156, icon: "box",    desc: "Charters, milestones" },
  { id: "t-fac",  name: "Facilities",      color: "oklch(0.70 0.10 200)", count: 124, icon: "building",desc: "Offices, access, travel" },
];

const PINNED = [
  { q: "Parental leave eligibility (US)", a: "A_parental" },
  { q: "Client-dinner expense limit",     a: "A_expense" },
  { q: "How to request production access", a: "A_prod" },
];

const RECENT = [
  { q: "Home-office setup reimbursement", time: "2d", a: "A_expense" },
  { q: "Hotfix outside the release window", time: "5d", a: "A_prod" },
  { q: "PTO carryover into 2026", time: "1w", a: "A_pto" },
];

/* ---------- Home suggestions ---------- */
const HOME = {
  role: [
    { q: "Summarize the 2026 parental-leave policy changes", a: "A_parental", meta: "Benefits" },
    { q: "What's the approval chain for opening a new req?", meta: "Hiring" },
    { q: "Where are signed offer letters stored?", meta: "Hiring" },
  ],
  updated: [
    { q: "Expense Policy — what changed this quarter?", a: "A_expense", badge: "updated 3d", kind: "fresh" },
    { q: "On-call rotation & break-glass access", a: "A_prod", badge: "updated 6d", kind: "fresh" },
    { q: "Deployment runbook for the new pipeline", badge: "updated 1w", kind: "fresh" },
  ],
  trending: [
    { q: "How do I expense a client dinner?", a: "A_expense", badge: "asked 34×", kind: "hot" },
    { q: "When is the next pay date?", badge: "asked 28×", kind: "hot" },
    { q: "How much PTO carries into 2026?", a: "A_pto", badge: "asked 21×", kind: "hot" },
  ],
};

/* ---------- Source pages (OneNote-style) ---------- */
const SOURCES = {
  S1: {
    notebook: "People & HR", section: "Benefits", page: "Parental Leave (US)",
    editor: "Dana Whitfield", init: "DW", edited: "3 months ago", editedFull: "Feb 24, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Eligibility" },
      { p: 'All regular full-time employees in the United States are eligible for <mark>16 weeks of fully paid parental leave</mark> as a primary caregiver, or 8 weeks as a secondary caregiver, after 90 days of continuous employment.' },
      { p: "Leave applies equally to birth, adoption, and foster placement. Part-time employees scheduled for 20+ hours/week accrue a prorated entitlement." },
      { h: "How it can be taken" },
      { p: "Leave may be taken continuously or intermittently in blocks of no less than one week, and must be completed within 12 months of the qualifying event." },
    ],
  },
  S2: {
    notebook: "People & HR", section: "Leave & Absence", page: "Filing a Leave Claim in Workday",
    editor: "Sofia Crane", init: "SC", edited: "8 weeks ago", editedFull: "Apr 2, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Submitting your claim" },
      { p: 'Open Workday → <strong>Time Off & Leave</strong> → <mark>Request Leave of Absence</mark>, then select "Parental." Attach supporting documentation (e.g. due-date confirmation) at least 30 days before your intended start date where possible.' },
      { p: "Your People Ops partner reviews the request within 2 business days and confirms pay continuation. Payroll is notified automatically." },
    ],
  },
  S3: {
    notebook: "People & HR", section: "Leave & Absence", page: "Leave of Absence — Coordination",
    editor: "Dana Whitfield", init: "DW", edited: "6 weeks ago", editedFull: "Apr 18, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Manager notification" },
      { p: 'Notify your manager in writing <mark>at least 30 days before</mark> the leave begins so coverage and a handover plan can be arranged. For unforeseeable events, notify as soon as practicable.' },
      { p: "Managers should not approve or deny leave directly — eligibility is confirmed by People Ops." },
    ],
  },
  S4: {
    notebook: "Finance", section: "Expenses & Travel", page: "Expense Policy — Meals & Entertainment",
    editor: "Marcus Lendt", init: "ML", edited: "3 days ago", editedFull: "May 27, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Client meals" },
      { p: 'Business meals with clients or candidates are reimbursable up to <mark>$120 per person</mark>, including tax and tip. Alcohol is permitted for client entertainment but capped at two drinks per attendee.' },
      { p: "Attach an itemized receipt and list every attendee in Concur. Meals above the cap require VP approval before submission." },
    ],
  },
  S5: {
    notebook: "Finance", section: "Expenses & Travel", page: "Corporate Card Guidelines",
    editor: "Marcus Lendt", init: "ML", edited: "7 weeks ago", editedFull: "Apr 9, 2026",
    relevantIdx: 0,
    doc: [
      { h: "Reconciliation" },
      { p: 'Corporate-card charges must be itemized and reconciled in Concur within <mark>30 days</mark>. Unreconciled charges past 60 days may be deducted via payroll.' },
    ],
  },
  S6: {
    notebook: "IT & Security", section: "Access", page: "Production Access Requests",
    editor: "Nadia Okafor", init: "NO", edited: "5 weeks ago", editedFull: "Apr 25, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Requesting standing access" },
      { p: 'File an access request in <strong>AccessHub</strong> selecting the target service and role. Production database access requires <mark>manager + service-owner approval</mark> and a completed data-handling attestation.' },
      { p: "Standing access is reviewed quarterly and auto-expires after 90 days of inactivity." },
    ],
  },
  S7: {
    notebook: "Engineering", section: "Platform", page: "On-call & Break-glass Access",
    editor: "Reuben Acosta", init: "RA", edited: "6 days ago", editedFull: "May 24, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Break-glass during incidents" },
      { p: 'On-call engineers can elevate to production using <mark>break-glass access</mark> in AccessHub, which grants a time-boxed 4-hour session. Every break-glass session is logged and reviewed in the incident retro.' },
      { p: "Use break-glass only during an active Sev-1/Sev-2; for routine work, request standing access instead." },
    ],
  },
  S8: {
    notebook: "People & HR", section: "Benefits", page: "PTO Policy 2026",
    editor: "Dana Whitfield", init: "DW", edited: "3 weeks ago", editedFull: "May 9, 2026",
    relevantIdx: 1,
    doc: [
      { h: "Carryover" },
      { p: 'Employees may carry over <mark>up to 5 unused PTO days</mark> into the following calendar year. Carried days must be used by March 31 or they are forfeited.' },
      { p: "Accrual continues at 1.67 days/month for employees with under 5 years of tenure." },
    ],
  },
};

/* ---------- Canned answers ---------- */
const ANSWERS = {
  A_parental: {
    q: "How much parental leave am I eligible for, and how do I file?",
    coverage: 3, freshness: "Source updated 3 months ago", fresh_warn: false,
    sources: ["S1", "S2", "S3"],
    followups: [
      "How does this differ for our Germany office?",
      "Can I take the leave intermittently?",
      "What happens to my RSU vesting during leave?",
    ],
    html: `
      <p>As a regular full-time US employee, you're eligible for <strong>16 weeks of fully paid parental leave</strong> as a primary caregiver, or <strong>8 weeks</strong> as a secondary caregiver, once you've completed 90 days of continuous employment.<span class="cite" data-c="1">1</span> This applies equally to birth, adoption, and foster placement.</p>
      <h4>How to file</h4>
      <ul>
        <li>In <strong>Workday</strong>, go to <em>Time Off &amp; Leave → Request Leave of Absence</em> and choose "Parental."<span class="cite" data-c="2">2</span></li>
        <li>Attach supporting documentation and submit <strong>at least 30 days before</strong> your intended start date where possible.<span class="cite" data-c="2">2</span></li>
        <li>Notify your manager in writing on the same timeline so a coverage and handover plan can be arranged.<span class="cite" data-c="3">3</span></li>
      </ul>
      <p>Your People Ops partner confirms eligibility and pay continuation within two business days — managers don't approve leave directly.<span class="cite" data-c="3">3</span></p>`,
  },
  A_expense: {
    q: "How do I expense a client dinner?",
    coverage: 2, freshness: "Source updated 3 days ago", fresh_warn: false,
    sources: ["S4", "S5"],
    followups: ["What's the cap for team dinners?", "Can I expense alcohol?", "How do I add attendees in Concur?"],
    html: `
      <p>Client meals are reimbursable up to <strong>$120 per person</strong>, inclusive of tax and tip. Alcohol is allowed for client entertainment but capped at two drinks per attendee.<span class="cite" data-c="1">1</span></p>
      <ul>
        <li>Attach an <strong>itemized receipt</strong> and list every attendee in Concur.<span class="cite" data-c="1">1</span></li>
        <li>If you paid on a corporate card, reconcile the charge in Concur within <strong>30 days</strong>.<span class="cite" data-c="2">2</span></li>
      </ul>
      <p>Anything above the $120/person cap needs VP approval before you submit.<span class="cite" data-c="1">1</span></p>`,
  },
  A_prod: {
    q: "How do I request production access?",
    coverage: 2, freshness: "Source updated 5 weeks ago", fresh_warn: false,
    sources: ["S6", "S7"],
    followups: ["How do I get break-glass during an incident?", "How long does standing access last?", "Who are the service owners?"],
    html: `
      <p>For standing access, file a request in <strong>AccessHub</strong>, selecting the target service and role. Production <em>database</em> access requires <strong>manager and service-owner approval</strong> plus a completed data-handling attestation.<span class="cite" data-c="1">1</span></p>
      <p>During an active Sev-1/Sev-2, on-call engineers can instead use <strong>break-glass access</strong> for a time-boxed 4-hour session — every session is logged and reviewed in the incident retro.<span class="cite" data-c="2">2</span></p>
      <p>Standing access is reviewed quarterly and auto-expires after 90 days of inactivity.<span class="cite" data-c="1">1</span></p>`,
  },
  A_pto: {
    q: "How much PTO carries into 2026?",
    coverage: 1, freshness: "Source updated 14 months ago", fresh_warn: true,
    sources: ["S8"],
    followups: ["When does carried PTO expire?", "What's the monthly accrual rate?", "Does PTO pay out when I leave?"],
    html: `
      <p>You can carry over <strong>up to 5 unused PTO days</strong> into the next calendar year. Carried days must be used by <strong>March 31</strong> or they're forfeited.<span class="cite" data-c="1">1</span></p>
      <p>Accrual continues at 1.67 days/month for employees with under five years of tenure.<span class="cite" data-c="1">1</span></p>`,
  },
};

/* ---------- Keyword router for free-typed questions ---------- */
const ROUTES = [
  { a: "A_parental", kw: ["parental", "maternity", "paternity", "newborn", "baby", "adoption"] },
  { a: "A_expense",  kw: ["expense", "dinner", "meal", "client", "reimburse", "concur", "receipt", "travel"] },
  { a: "A_prod",     kw: ["production", "prod access", "database access", "break-glass", "on-call", "deploy", "access"] },
  { a: "A_pto",      kw: ["pto", "vacation", "carryover", "carry over", "time off", "holiday"] },
];
