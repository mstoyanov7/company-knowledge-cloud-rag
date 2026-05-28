# Phase 8: Custom Topic-First Frontend

## Reason for this phase

The project should no longer use Open WebUI as the user-facing interface. The system needs its own genuine, user-friendly frontend that is designed specifically for company knowledge assistance.

The frontend must not look like a generic chatbot. It should guide the user through topics first, then allow them to ask a question inside the selected topic. This makes the system feel more controlled, structured, and useful inside a company environment.

## Core change

Replace this user-facing flow:

```text
Open WebUI -> user asks any question -> RAG API answers
```

with this flow:

```text
Custom frontend -> user selects topic -> user asks question inside that topic -> RAG API retrieves only relevant scoped knowledge -> answer with citations
```

Open WebUI should be removed from the user-facing product. The RAG API, sync worker, PostgreSQL, Redis, Qdrant and OneNote sync remain useful and should not be redesigned unless needed.

---

## Product goal

Build a clean company knowledge assistant where users first choose the area they need help with, such as:

- Project deployment
- HR questions
- Finances
- Installation guides
- Internal tools
- Company policies
- Troubleshooting
- Onboarding steps

After choosing a topic, the user sees a minimal question interface related only to that topic.

The UI must feel like a guided knowledge assistant, not like a normal chat app.

---

## UI principles

### 1. Topic-first experience

The first screen should ask:

```text
What do you need help with?
```

Then show large, clean topic cards.

Each card should contain only:

- topic name
- one short description
- optional small icon

Example:

```text
Project Deployment
Ask about deployment steps, environments, release process, and rollback instructions.
```

### 2. No unnecessary information

Do not show:

- model name
- token count
- debug data
- retrieval score
- raw chunk IDs
- system prompts
- backend metadata
- irrelevant settings
- generic AI branding
- complex sidebars

The user should only see what helps them complete the task.

### 3. Not a regular chatbot

Avoid a classic full-page chat layout with many bubbles and generic assistant branding.

Preferred layout:

```text
Topic selection screen
-> focused question screen
-> answer card with citations
-> suggested follow-up actions
```

The answer should look like a knowledge card, not only a chat message.

### 4. User feels in control

The user should feel that they are selecting the knowledge area first, not blindly asking an AI.

The frontend should show:

- selected topic
- option to change topic
- question input
- clear answer
- cited source pages/files
- suggested related questions inside the same topic

### 5. Company-friendly design

Use a clean professional UI suitable for internal company tools.

Style direction:

- simple layout
- calm colors
- rounded cards
- readable typography
- no clutter
- no unnecessary animations
- responsive desktop-first design

---

## Required architecture update

Add a new frontend app.

Recommended path:

```text
apps/company-knowledge-ui
```

Recommended frontend stack:

```text
React + TypeScript + Vite
```

The frontend should call the existing FastAPI RAG backend.

Do not remove the backend architecture.

Keep:

```text
services/rag-api
services/sync-worker
services/graph-connectors
libs/shared-schemas
PostgreSQL
Redis
Qdrant
```

Remove or de-prioritize:

```text
apps/openwebui
Open WebUI frontend wiring
Open WebUI Pipe as primary user interface
```

Open WebUI can remain in the repo as legacy/reference, but the final diploma product should present the custom frontend.

---

## Required backend update

The RAG API must support topic-aware retrieval.

Add topic configuration.

Example file:

```text
config/topics.json
```

Example:

```json
[
  {
    "id": "project-deployment",
    "name": "Project Deployment",
    "description": "Deployment steps, environments, releases, rollback, and production checks.",
    "acl_tags": ["public", "employees", "engineering"],
    "source_filters": ["onenote", "sharepoint"],
    "retrieval_tags": ["deployment", "release", "environment", "rollback", "production"],
    "suggested_questions": [
      "How do I deploy the project?",
      "What should I check before production release?",
      "How do I rollback a failed deployment?"
    ]
  },
  {
    "id": "hr",
    "name": "HR Questions",
    "description": "Leave policy, onboarding, benefits, internal rules, and employee documents.",
    "acl_tags": ["public", "employees"],
    "source_filters": ["onenote", "sharepoint"],
    "retrieval_tags": ["hr", "leave", "benefits", "employee", "onboarding"],
    "suggested_questions": [
      "What documents do I need for onboarding?",
      "How do I request paid leave?",
      "Where can I find employee policies?"
    ]
  },
  {
    "id": "installation-guides",
    "name": "Installation Guides",
    "description": "Setup instructions, software installation, tools, and configuration guides.",
    "acl_tags": ["public", "employees", "engineering"],
    "source_filters": ["onenote", "sharepoint"],
    "retrieval_tags": ["install", "setup", "configuration", "tools"],
    "suggested_questions": [
      "How do I install the required tools?",
      "How do I configure the development environment?",
      "What setup steps should I follow first?"
    ]
  }
]
```

Add API endpoints:

```http
GET /api/v1/topics
POST /api/v1/answer
```

The existing `/api/v1/answer` should accept a new `topic_id` field:

```json
{
  "topic_id": "project-deployment",
  "question": "How do I deploy the project?",
  "user_context": {
    "acl_tags": ["public", "employees", "engineering"]
  }
}
```

The backend should use the selected topic to:

- filter retrieval
- prioritize topic tags
- limit suggested follow-up questions
- improve prompt context
- avoid unrelated answers from other company areas

---

## Required frontend screens

### Screen 1: Topic selection

Purpose:

Let the user choose the area they need help with.

Must include:

- title: "What do you need help with?"
- topic cards loaded from `GET /api/v1/topics`
- search/filter for topics if there are many
- no chat input yet

Example cards:

```text
Project Deployment
HR Questions
Finances
Installation Guides
Internal Tools
Troubleshooting
```

### Screen 2: Topic question screen

Purpose:

Ask a question inside the selected topic.

Must include:

- selected topic name
- topic description
- change topic button
- question input
- suggested questions
- answer area

Do not show backend/debug metadata.

### Screen 3: Answer card

Purpose:

Show answer in a clean useful way.

Must include:

- answer title
- answer body
- source citations
- source page/file names
- last updated timestamp if available
- suggested follow-up questions

The answer should not look like generic chat bubbles.

Suggested layout:

```text
[Selected Topic]

Question:
[ input box ]

Answer:
[ knowledge card ]

Sources:
- OneNote page: ...
- Attached Word document: ...
- SharePoint file: ...

Related questions:
[ suggestion ] [ suggestion ] [ suggestion ]
```

---

## Data contract

### Topic object

```ts
type Topic = {
  id: string;
  name: string;
  description: string;
  icon?: string;
  suggested_questions: string[];
};
```

### Answer request

```ts
type TopicAnswerRequest = {
  topic_id: string;
  question: string;
};
```

### Answer response

Use the existing backend response shape:

```ts
type AnswerResponse = {
  answer: string;
  citations: Citation[];
  retrieval_meta?: unknown;
  metadata?: unknown;
};
```

But the frontend should only render:

- `answer`
- `citations.title`
- `citations.source_system`
- `citations.source_url`
- `citations.section_path`
- `citations.last_modified_utc`

Do not render debug metadata in the normal user UI.

---

## Topic-aware retrieval behavior

When a topic is selected, the backend should:

1. Load topic config by `topic_id`.
2. Add topic tags to retrieval query context.
3. Apply topic `source_filters`.
4. Apply allowed ACL tags from user context/auth.
5. Retrieve only within the selected topic scope.
6. Return answer and citations.
7. Return suggested follow-up questions from the selected topic.

The selected topic must never bypass ACL filtering.

Correct order:

```text
user identity / ACL
-> selected topic scope
-> retrieval
-> rerank
-> answer
```

Wrong order:

```text
retrieval from all data
-> topic filtering after answer
```

---

## Suggested folder structure

```text
apps/company-knowledge-ui/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    api/
      client.ts
      topics.ts
      answers.ts
    components/
      TopicCard.tsx
      TopicGrid.tsx
      QuestionPanel.tsx
      AnswerCard.tsx
      CitationList.tsx
      SuggestedQuestions.tsx
      EmptyState.tsx
      LoadingState.tsx
      ErrorState.tsx
    pages/
      TopicSelectionPage.tsx
      TopicAskPage.tsx
    styles/
      global.css
```

Backend additions:

```text
services/rag-api/app/rag_api/api/routes/topics.py
services/rag-api/app/rag_api/services/topic_service.py
services/rag-api/app/rag_api/services/topic_loader.py
libs/shared-schemas/python/shared_schemas/topics.py
config/topics.json
```

---

## Definition of done

This phase is complete when:

1. Open WebUI is no longer the main visible user interface.
2. A custom frontend starts locally.
3. The first screen shows topic cards.
4. The user must select a topic before asking a question.
5. The question is sent to the backend with `topic_id`.
6. The backend applies topic-aware retrieval.
7. The answer is displayed as a clean knowledge card.
8. Citations are displayed clearly and minimally.
9. No unnecessary technical metadata is shown to the user.
10. The UI is suitable to show during the diploma defense.

---

## Codex prompt

```text
You are working in the repository company-knowledge-cloud-rag.

The project currently uses Open WebUI as the frontend, but this must change.

New goal:
Build a genuine custom frontend for the Cloud-RAG company knowledge assistant. The frontend must not look like a generic chatbot. It must be topic-first, minimal, user friendly, and suitable for company onboarding and internal knowledge search.

Important requirements:
1. Do not use Open WebUI as the user-facing interface anymore.
2. Add a new frontend app under apps/company-knowledge-ui.
3. Use React + TypeScript + Vite unless the repo already has a stronger frontend convention.
4. The first screen must ask the user to choose a topic before asking a question.
5. Topics should represent company knowledge areas such as Project Deployment, HR Questions, Finances, Installation Guides, Internal Tools, Troubleshooting, and Onboarding.
6. Load topics from the backend using GET /api/v1/topics.
7. Add a topic config file, preferably config/topics.json.
8. Add backend topic models and a topic service.
9. Extend the answer request flow so the frontend sends topic_id with the question.
10. The backend must use topic_id to scope retrieval, prioritize topic tags, apply source filters, and improve answer relevance.
11. Topic filtering must never bypass ACL filtering. Correct order is user ACL -> topic scope -> retrieval -> rerank -> answer.
12. The UI must not show model names, token counts, raw chunk IDs, retrieval scores, debug metadata, system prompts, or other unnecessary technical information.
13. The answer must be displayed as a clean knowledge card, not as a generic chat bubble.
14. Show citations in a minimal useful way: title, source type, section/path, link, and last updated date if available.
15. Show suggested follow-up questions related to the selected topic.
16. Add a Change Topic action.
17. Keep the existing RAG API, sync worker, PostgreSQL, Redis, Qdrant, OneNote sync, and SharePoint sync.
18. Do not redesign the ingestion pipeline.
19. Keep Open WebUI files only as legacy/reference if needed, but the final product should use the new custom frontend.
20. Add clear run instructions.

Implementation tasks:
- Create apps/company-knowledge-ui with React + TypeScript + Vite.
- Add topic selection page.
- Add topic question page.
- Add answer card component.
- Add citation list component.
- Add suggested questions component.
- Add minimal professional styling.
- Add backend topic schemas.
- Add GET /api/v1/topics.
- Extend POST /api/v1/answer to accept topic_id.
- Add topic-aware retrieval logic.
- Add config/topics.json with starter topics.
- Update README with new frontend instructions.
- Add tests for topic loading and topic-aware answer request behavior.

Return:
1. all created/updated files,
2. run instructions,
3. environment variables if any,
4. known limitations,
5. next recommended improvements.
```

---

## Recommended next improvements after this phase

After this phase works, improve:

1. Topic management from admin UI instead of static JSON.
2. Per-topic icons and branding.
3. Per-topic source restrictions.
4. Per-topic suggested questions generated from indexed content.
5. User feedback buttons:
   - helpful
   - not helpful
   - wrong source
   - missing information
6. Analytics:
   - most asked topics
   - unanswered questions
   - stale sources
7. Better answer evaluation per topic.
