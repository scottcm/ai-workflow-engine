# Standards Overview

This directory contains **standards** used by the AI Workflow Engine
to drive realistic code generation for a multi-tenant Java / Spring / JPA
environment.

These documents are **intentionally scoped**:

- They capture **common, expected conventions** for a typical Spring + JPA,
  multi-tenant backend.
- They are **not an exhaustive set of organization-wide standards**.
- Their purpose is to provide **enough structure** for the engine to generate
  credible, production-style code and planning documents, and to validate that
  the project works end-to-end.

In a real product, you would typically have additional standards for security,
observability, testing, and other cross-cutting concerns. For this project,
the focus is on the parts required to generate and validate code against a real
database.

## Files in this bundle

- `ARCHITECTURE_AND_MULTITENANCY.md`  
  High-level architecture rules and multi-tenancy model (schemas, tenant
  identity, RLS expectations).

- `BOILERPLATE_AND_DI.md`  
  Guidelines for dependency injection, common wiring patterns, and how to avoid
  repetitive boilerplate in Spring-based applications.

- `JPA_AND_DATABASE.md`  
  Canonical rules for mapping entities, relationships, timestamps, and IDs to
  the database using JPA/Hibernate, including expectations for schema/table
  declarations.

- `NAMING_AND_API.md`  
  Naming conventions for classes, methods, fields, and public-facing APIs,
  plus basic guidance on how HTTP and domain APIs should align.

- `ORG.md`  
  Organization-wide conventions that apply across languages and layers
  (general coding expectations, documentation tone, etc.).

- `PACKAGES_AND_LAYERS.md`  
  Folder/package structure and layering rules (API, domain, service,
  persistence, etc.), including which dependencies are allowed between layers.

- `code-gen-request.md`  
  A template that describes how code generation requests should be structured
  for this profile (metadata, attached standards, and expectations for output).

## How these standards are used

The AI Workflow Engine attaches one or more of these documents to a request
when asking an AI model to:

- Analyze a database schema and produce a planning document
- Generate domain-layer code (entities and repositories)
- Review or refactor existing code for consistency with the standards

The standards files act as **ground truth** for conventions. They are written
for both humans and AI:

- Humans can read them as normal engineering standards.
- AI models can consume them as **instructions and constraints** when
  generating or reviewing code.

Because these standards are intentionally minimal, they are a good fit for:

- Demonstrating that the AI Workflow Engine can respect real-world conventions.
- Keeping the token footprint small enough for repeated use in prompts.
- Serving as a starting point that can be extended in a real product.

## Scope and limitations

- These documents **do not** attempt to cover every concern of a real system
  (security, observability, performance tuning, exhaustive testing strategies,
  etc.).
- They are focused on the **domain and persistence layers** for a
  multi-tenant Spring + JPA backend.
- In a production setting, you would extend this bundle with additional
  standards as needed, rather than treating this set as complete.
