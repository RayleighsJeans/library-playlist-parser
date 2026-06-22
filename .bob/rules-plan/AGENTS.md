# Project Architecture Rules (Non-Obvious Only)

## Non-Obvious Architectural Constraints

### Sequential Matching Strategy Design
- `find_match()` uses 5 strategies in specific order - not parallel
- Order matters: exact → partial → albumartist → fuzzy → similarity
- Each strategy builds on previous failures
- Changing order will break diagnostic failure reasons
- Similarity threshold (50%) is hardcoded - no configuration option

### Cache Index Structure
- `album_artist_index` provides O(1) lookup by album artist
- But matching still iterates all cache entries for other strategies
- Index only optimizes specific use cases, not general matching
- This is why large libraries still take time despite indexing

### Dual Cache Building Architecture
- Two separate methods: `build_cache_from_paths()` and `build_cache_from_directory()`
- `build_cache()` dispatcher method chooses based on parameter
- This dual approach enables both CLI and programmatic use
- Not obvious from external API - looks like single method

### Metadata Normalization Coupling
- Normalization happens during cache building, not during matching
- Pre-normalized strings stored as `*_norm` fields in cache
- Changing normalization requires cache rebuild
- No way to re-normalize existing cache without rebuilding

### Failure Reason String Format
- Failure reasons are structured strings, not error codes
- Format used by logging and unmatched log generation
- Changing format breaks log parsing in downstream tools
- Diagnostic information embedded in human-readable text

### Path Parser Format System
- `FORMATS` dictionary is class-level, shared across instances
- Adding formats at runtime affects all parser instances
- Regex patterns must use non-greedy matching (`.+?`)
- Greedy matching will consume delimiters and break parsing

### Cache File Atomic Writes
- `save_cache()` writes to `.tmp` file first, then uses `replace()` for atomic rename
- Prevents corruption if process interrupted during write
- This architectural decision ensures cache integrity across all operations
