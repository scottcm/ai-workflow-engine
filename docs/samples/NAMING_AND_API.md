# Naming And Api (AI-Optimized)
> Canonical rules for naming, controllers, DTOs, mappers, and exceptions.

### Requirements: Core Naming Conventions

- **Entities**
    - MUST match the **singular table name** exactly.
    - MUST NOT use suffixes such as `Entity`, `Model`, `Record`, `DO`, etc.
- **Repositories**
    - MUST use the `Repository` suffix.
- **Services**
    - MUST use the `Service` suffix.
- **Tests**
    - MUST use the `Test` suffix and map 1:1 to the class under test.

**Examples from this codebase:**

| Table | Entity | Repository | Service |
|-------|--------|------------|---------|
| `app.tenants` | `Tenant` | `TenantRepository` | `TenantService` |
| `app.products` | `Product` | `ProductRepository` | `ProductService` |
| `global.tiers` | `Tier` | `TierRepository` | `TierService` |

### Requirements: Controller & DTO Naming

- **Controllers**
    - MUST use the `*Controller` suffix.
    - MUST remain thin—validation, parameter extraction, delegation only.
- **External API DTOs**
    - MUST use `*Request` and `*Response`.
    - MUST live under `…api.dto.<bounded_context>`.
    - SHOULD use Java **records** when appropriate.
- **Internal-only DTOs**
    - MAY use `*Dto`.
    - MUST NOT be part of external API surfaces.

**Examples from this codebase:**

| Entity | Controller | Request DTO | Response DTO |
|--------|------------|-------------|--------------|
| `Product` | `ProductController` | `CreateProductRequest` | `ProductResponse` |
| `Tenant` | `TenantController` | `CreateTenantRequest` | `TenantResponse` |
| `Tier` | `TierController` | `CreateTierRequest` | `TierResponse` |

**DTO Package Locations:**
- `com.example.app.api.dto.product.CreateProductRequest`
- `com.example.app.api.dto.product.ProductResponse`
- `com.example.app.api.dto.tenant.CreateTenantRequest`
- `com.example.app.api.dto.tenant.TenantResponse`

### Requirements: Mapper Naming

- All entity↔DTO mapping MUST be performed in `*Mapper` classes.
- Mappers SHOULD live in a dedicated mapper package.
- Services & controllers MUST NOT contain inline/ad-hoc mapping logic.

**Examples from this codebase:**

| Entity | Mapper |
|--------|--------|
| `Product` | `ProductMapper` |
| `Tenant` | `TenantMapper` |
| `Tier` | `TierMapper` |

**Mapper Package Location:** `com.example.app.mapper`

### Requirements: Exception Naming

- Domain exceptions MUST end with `Exception`.
- API exceptions SHOULD be translated via a global `@ControllerAdvice`.

**Examples:**
- `ProductNotFoundException`
- `TenantNotFoundException`
- `DuplicateSkuException`
