# Org (AI-Optimized)
These standards define **mandatory and recommended** practices for all Java code across the organization.  
They apply to **all repositories** unless an exception is explicitly approved (ADR required).  
All requirement keywords follow **RFC 2119**.

### Requirements
- Classes MUST use `UpperCamelCase`.
- Interfaces MUST use `UpperCamelCase` and MUST NOT use an `I` prefix.
- Methods MUST use `lowerCamelCase`.
- Variables (fields & locals) MUST use `lowerCamelCase`.
- Constants MUST use `ALL_CAPS_WITH_UNDERSCORES`.
- Packages MUST use `all.lowercase.with.dots`.

### Requirements
- Persistent entity class names SHOULD be the **singular UpperCamelCase** form of the conceptual entity.  
  Example: `identity_providers` → `IdentityProvider`.
- Entities MUST avoid suffixes such as `Entity`, `Model`, `Record`, `DO`, etc.

### Requirements
- Indentation MUST be 4 spaces.
- Braces MUST follow K&R / 1TBS.
- Imports MUST follow standard grouping (Static → Java → 3rd Party → App).
- `System.out` and `printStackTrace` MUST NOT appear in generated code.

### Requirements
- SLF4J MUST be used for all logging.
- `System.out.println` is forbidden.
- Logger declaration SHOULD follow:  
  `private static final Logger log = LoggerFactory.getLogger(CurrentClass.class);`
- Correct log levels MUST be used: DEBUG (diagnostic), INFO (ops), WARN (recoverable), ERROR (failure).

### Requirements
- Prefer unchecked (`RuntimeException`) over checked exceptions.
- Checked exceptions MUST NOT be added without justification.
- Methods MUST NOT throw generic `Exception`.
- Catch blocks MUST NOT swallow exceptions.
- Wrapped exceptions MUST preserve the cause.

### Requirements
- Constructor injection MUST be used for all dependencies.
- Field injection (`@Autowired`) is forbidden.
- Lombok `@RequiredArgsConstructor` SHOULD be used.
- Circular dependencies MUST be avoided.

### Requirements
- **Testing:** JUnit 5 and AssertJ MUST be used.
- **Lombok:** Permitted and encouraged for boilerplate elimination.
- **Logging:** SLF4J is the only allowed logging façade.

### Requirements
- Classes SHOULD have a single clear responsibility (SRP).
- Large procedural blocks MUST be refactored into helper methods.
- Public APIs MUST remain stable; internals MUST be private or package-private.
- Immutability SHOULD be preferred when practical.
