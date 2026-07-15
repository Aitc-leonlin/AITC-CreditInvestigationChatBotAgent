# Backend Modules

This folder contains feature modules that own their API, schemas, services, repositories, models, and module-specific core utilities.

## Current Modules

- `membership`: membership, authentication, RBAC, menu permissions, organization, audit, and notification admin APIs.
- `chatbot`: chatbot HTTP APIs, expert-knowledge APIs, warehouse-data APIs, request/response schemas, LangGraph agent flow, LLM provider, mappings, and chatbot-specific helper services.
- `report_generator`: report generator HTTP APIs, report history/dashboard logic, LLM conclusion service, and DOCX chapter generation services.

## Placement Rules

- Put new feature-specific API routers under `src/features/<module>/api`.
- Put business logic under `src/features/<module>/services`.
- Put request/response Pydantic schemas under `src/features/<module>/schemas`.
- Put database access classes under `src/features/<module>/repositories`.
- Put module-specific reusable utilities under `src/features/<module>/core`.
- Put cross-module utilities under `src/shared`, not inside one feature module.

XBRL resource files used by chatbot and report generation are stored under `src/features/chatbot/services`. New feature code should go under `src/features`.
