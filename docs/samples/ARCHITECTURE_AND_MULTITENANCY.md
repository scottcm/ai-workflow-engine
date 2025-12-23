# Architecture and Multitenancy (AI-Optimized)

## Tenant Model Requirements

- **`tenant_id` is the canonical tenant identifier.**
- Tenant table: `app.tenants`
- Tenant-scoped tables contain a `tenant_id` column referencing `app.tenants(id)`

**Entity Classification in This Codebase:**

| Entity | Table | Type | tenant_id column? |
|--------|-------|------|-------------------|
| `Tenant` | `app.tenants` | Tenant entity | No (IS the tenant) |
| `Product` | `app.products` | Tenant-scoped | Yes |
| `Tier` | `global.tiers` | Global/shared | No |

---

## Connection Pool Requirements

### Admin / Provisioning Repositories
- MUST use the **Admin Connection Pool**.
- Admin connections **bypass RLS**.
- MAY ONLY be used for:
  - tenant creation
  - provisioning tasks
  - administrative metadata
- MUST NOT be used for tenant-scoped runtime operations.

**Example - Admin operations:**
```java
// TenantService.java - uses admin pool
@AdminTransactional
public Tenant createTenant(CreateTenantRequest request) {
    // Admin pool bypasses RLS - can create tenants
}
```

### Tenant Runtime Repositories
- MUST use the **Tenant Connection Pool**.
- RLS MUST be **enabled and enforced** via:
  ```sql
  SET LOCAL app.current_tenant_id = :tenantId
  ```
- All API-serving business logic MUST run in the tenant pool context.
- A single method MUST NOT mix admin-pool and tenant-pool operations.
  - If both are required, they MUST be split into separate service-layer methods.

**Example - Tenant-scoped operations:**
```java
// ProductService.java - uses tenant pool with RLS
@Transactional
public Product createProduct(CreateProductRequest request) {
    // RLS automatically filters to current tenant
    // No need to pass tenant_id - it's set at connection level
}

@Transactional(readOnly = true)
public Optional<Product> findBySku(String sku) {
    // RLS ensures only current tenant's products are visible
    return productRepository.findBySku(sku);
}
```

**Example - Global entity access from tenant context:**
```java
// ProductService.java
@Transactional
public Product assignTier(UUID productPublicId, String tierCode) {
    Product product = productRepository.findByPublicId(productPublicId)
        .orElseThrow(() -> new ProductNotFoundException(productPublicId));
    
    // Global tiers are visible to all tenants (no RLS on global.tiers)
    Tier tier = tierRepository.findByCode(tierCode)
        .orElseThrow(() -> new TierNotFoundException(tierCode));
    
    product.setTier(tier);
    return product;
}
```

---

## Transaction Requirements
- Transactions MUST be declared **only** in the Service Layer.
- Controllers and repositories MUST NOT declare transactional boundaries.
- Tenant-scoped operations:
  - MUST use `@Transactional` with the **tenant pool**.
  - MUST NOT disable or bypass RLS.
- Admin/provisioning operations:
  - MUST use `@AdminTransactional`.
  - SHOULD use `REQUIRES_NEW` when it prevents tenant/tenant pool mixing.
- Long-running operations MUST use batching/pagination.
- Transactions MUST NOT be used to circumvent RLS protections.

**Examples:**
```java
// CORRECT: Service layer declares transaction
@Service
@RequiredArgsConstructor
public class ProductService {
    
    @Transactional
    public Product create(CreateProductRequest request) { ... }
    
    @Transactional(readOnly = true)
    public Page<Product> listActive(Pageable pageable) { ... }
}

// WRONG: Controller declares transaction
@RestController
public class ProductController {
    @Transactional  // FORBIDDEN - move to service
    @PostMapping
    public ProductResponse create(...) { ... }
}
```

---

## API Signature & Naming Requirements

Because RLS handles tenant isolation at the database level, **tenant_id is NOT passed in application-layer method signatures** for tenant-scoped operations.

**Service Layer - Tenant-scoped operations:**
```java
// CORRECT: No tenant_id parameter - RLS handles isolation
Product create(CreateProductRequest request);
Optional<Product> findByPublicId(UUID publicId);
Optional<Product> findBySku(String sku);
Page<Product> listActive(Pageable pageable);
```

**Service Layer - Admin operations (when tenant_id IS required):**
```java
// Admin context may need explicit tenant reference
@AdminTransactional
List<Product> findAllProductsForTenant(Long tenantId);  // Admin reporting
```

**Method verbs MUST be consistent across the codebase:**
- `createX`, `updateX`, `deleteX`, `getX`, `listX`

**Examples:**
```java
// ProductService
Product createProduct(CreateProductRequest request);
Product updateProduct(UUID publicId, UpdateProductRequest request);
void deleteProduct(UUID publicId);
Optional<Product> getProduct(UUID publicId);
Page<Product> listProducts(Pageable pageable);

// TenantService (admin context)
Tenant createTenant(CreateTenantRequest request);
Optional<Tenant> getTenantByCode(String code);
```