# Boilerplate And Di (AI-Optimized)
> Canonical rules for boilerplate elimination, Lombok usage, and dependency-injection patterns.

### Requirements: Lombok Usage

- Lombok **is allowed and encouraged** to eliminate boilerplate.
- Allowed Lombok patterns:
    - `@Getter` / `@Setter` for entity accessors
    - `@NoArgsConstructor` / `@AllArgsConstructor` for JPA-required constructors
    - `@Builder` for complex construction and readability (DTOs, requests)
    - `@RequiredArgsConstructor` for constructor injection in services/controllers
    - `@Data` for simple immutable structures or DTO-like classes
- Lombok usage MUST be **consistent** across the codebase.
- Lombok MUST NOT hide domain logic—use only for boilerplate, not behavior.

**Example - Entity with Lombok:**
```java
@Entity
@Table(schema = "app", name = "products")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(name = "public_id", unique = true, nullable = false)
    private UUID publicId;
    
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "tenant_id", nullable = false)
    private Tenant tenant;
    
    // ... other fields
}
```

**Example - DTO with Lombok:**
```java
@Builder
public record CreateProductRequest(
    String sku,
    String name,
    String description,
    BigDecimal price
) {}

@Builder  
public record ProductResponse(
    UUID publicId,
    String sku,
    String name,
    String description,
    BigDecimal price,
    String tierCode,
    OffsetDateTime createdAt
) {}
```

### Requirements: Dependency Injection

- **Constructor Injection ONLY**
    - All Spring components (services, controllers, mappers, etc.) MUST use constructor injection.
    - `@RequiredArgsConstructor` is preferred for brevity and clarity.
- **Field Injection is forbidden**
    - `@Autowired` MUST NOT appear on fields.
    - Constructor-level `@Autowired` MAY be omitted when using `@RequiredArgsConstructor`.
- Injection MUST NOT be performed using setter methods.
- Components MUST depend only on required collaborators; avoid "kitchen sink" injection.

**Example - Service with constructor injection:**
```java
@Service
@RequiredArgsConstructor
public class ProductService {
    
    private final ProductRepository productRepository;
    private final TierRepository tierRepository;
    private final ProductMapper productMapper;
    
    @Transactional
    public ProductResponse createProduct(CreateProductRequest request) {
        Product product = productMapper.toEntity(request);
        product.setPublicId(UUID.randomUUID());
        product.setCreatedAt(OffsetDateTime.now());
        product.setUpdatedAt(OffsetDateTime.now());
        product.setActive(true);
        
        Product saved = productRepository.save(product);
        return productMapper.toResponse(saved);
    }
}
```

**Example - Controller with constructor injection:**
```java
@RestController
@RequestMapping("/api/products")
@RequiredArgsConstructor
public class ProductController {
    
    private final ProductService productService;
    
    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request) {
        ProductResponse response = productService.createProduct(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
    
    @GetMapping("/{publicId}")
    public ResponseEntity<ProductResponse> get(@PathVariable UUID publicId) {
        return productService.getProduct(publicId)
            .map(ResponseEntity::ok)
            .orElseThrow(() -> new ProductNotFoundException(publicId));
    }
}
```

**Example - Mapper with constructor injection:**
```java
@Component
@RequiredArgsConstructor
public class ProductMapper {
    
    public Product toEntity(CreateProductRequest request) {
        Product product = new Product();
        product.setSku(request.sku());
        product.setName(request.name());
        product.setDescription(request.description());
        product.setPrice(request.price());
        return product;
    }
    
    public ProductResponse toResponse(Product product) {
        return ProductResponse.builder()
            .publicId(product.getPublicId())
            .sku(product.getSku())
            .name(product.getName())
            .description(product.getDescription())
            .price(product.getPrice())
            .tierCode(product.getTier() != null ? product.getTier().getCode() : null)
            .createdAt(product.getCreatedAt())
            .build();
    }
}
```

### Anti-Patterns (FORBIDDEN)

```java
// WRONG: Field injection
@Service
public class ProductService {
    @Autowired  // FORBIDDEN
    private ProductRepository productRepository;
}

// WRONG: Setter injection
@Service
public class ProductService {
    private ProductRepository productRepository;
    
    @Autowired  // FORBIDDEN
    public void setProductRepository(ProductRepository repo) {
        this.productRepository = repo;
    }
}

// WRONG: Kitchen sink injection
@Service
@RequiredArgsConstructor
public class ProductService {
    private final ProductRepository productRepository;
    private final TenantRepository tenantRepository;  // Not used - remove
    private final TierRepository tierRepository;
    private final AuditService auditService;  // Not used - remove
    private final NotificationService notificationService;  // Not used - remove
}
```