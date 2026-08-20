## Purpose

Stores paper embeddings and serves similarity search over them, returning paper metadata with scores and vector-derived related paper ids.

## ADDED Requirements

### Requirement: Embedding index
The system SHALL index papers together with their embedding vectors for later similarity search.

#### Scenario: Index a batch
- **WHEN** a batch of papers with embeddings is indexed
- **THEN** each paper's embedding is searchable by subsequent queries

### Requirement: Similarity search
The system SHALL return the top-k papers most similar to a query vector, ranked by cosine similarity, each with metadata and score.

#### Scenario: Top-k search
- **WHEN** a search is performed with a query vector and top_k
- **THEN** the result contains up to top_k papers ordered by similarity score
- **AND** each result carries id, title, authors, abstract, score, and related_ids

### Requirement: Vector-derived related ids
The system SHALL compute and store, for each indexed paper, the ids of its top-5 vector neighbors (excluding itself).

#### Scenario: Related ids computed at index time
- **WHEN** a paper is indexed
- **THEN** its stored related_ids contain up to 5 neighboring paper ids computed by vector similarity
- **AND** the paper's own id is not among its related_ids

### Requirement: Paper fetch by id
The system SHALL return full paper metadata (id, title, authors, abstract) for a given paper id.

#### Scenario: Known paper
- **WHEN** a paper id that exists is requested
- **THEN** its metadata is returned

#### Scenario: Unknown paper
- **WHEN** a paper id that does not exist is requested
- **THEN** the result indicates the paper was not found

### Requirement: Vector store health
The system SHALL report whether the vector store is reachable.

#### Scenario: Healthy store
- **WHEN** the store is reachable
- **THEN** the health check reports success
