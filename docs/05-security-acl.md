# Security and ACL Strategy

## Principle

A shared chatbot must never answer from content the current user should not see.

## Minimal security model

Apply access control at two levels:

### 1. During indexing
Attach ACL metadata to every chunk.

Examples:

- tenant
- department
- site
- notebook
- visibility group
- source owner
- audience label

### 2. During retrieval
Filter candidate chunks by the current user's allowed ACL scope before final ranking.

## Identity propagation

When Open WebUI calls your RAG API, pass identity context such as:

- user id
- email
- tenant id
- group claims or role claims

## Security implementation notes

- never rely on the LLM to enforce permissions
- never send unauthorized chunks to the model
- log retrieval filters for audits
- keep citation output limited to allowed sources only

## Recommended prototype scope

For the diploma, start with a restricted onboarding knowledge scope:

- dedicated SharePoint onboarding sites
- dedicated onboarding notebooks
- limited employee audience

That reduces security risk and simplifies permission reasoning.
