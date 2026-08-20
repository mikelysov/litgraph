## Purpose

Persists the academic-paper knowledge graph and answers graph queries used to enrich search results with related papers and to render the graph visualization.

## ADDED Requirements

### Requirement: Paper upsert
The system SHALL store papers (id, title, authors) such that re-ingesting the same paper id updates the existing record instead of duplicating it.

#### Scenario: Re-ingest same paper
- **WHEN** a paper with an id that already exists is ingested
- **THEN** the stored paper is updated with the new title and authors
- **AND** no duplicate paper node is created

### Requirement: Entity linkage
The system SHALL store extracted entities (method/dataset/task/model) and link papers to entities via a role-annotated relationship.

#### Scenario: Paper links to extracted entities
- **WHEN** a paper is ingested with extracted entities
- **THEN** an entity node exists for each entity name+type pair
- **AND** the paper is linked to each entity with the corresponding role

#### Scenario: Entities shared across papers
- **WHEN** two papers reference the same entity
- **THEN** both papers link to a single shared entity node

### Requirement: Related papers by entity overlap
The system SHALL return paper ids sharing at least one entity with a given paper, ranked by overlap count.

#### Scenario: Overlap ranking
- **WHEN** related papers are requested for a given paper id
- **THEN** the result contains other papers sharing entities, ordered by descending number of shared entities
- **AND** the given paper id itself is excluded

### Requirement: Paper metadata lookup
The system SHALL return paper metadata (id, title, authors) for a list of paper ids.

#### Scenario: Lookup by ids
- **WHEN** metadata is requested for a list of known ids
- **THEN** each known id returns its title and authors
- **AND** unknown ids are omitted from the result

### Requirement: Shared-entity edges
The system SHALL return weighted edges between papers that share entities, where weight equals the number of shared entities.

#### Scenario: Edge computation
- **WHEN** edges are requested for a set of paper ids
- **THEN** an edge exists between each pair of papers sharing entities
- **AND** each edge carries its shared-entity count as weight

### Requirement: Graph health
The system SHALL report whether the graph store is reachable.

#### Scenario: Healthy store
- **WHEN** the store is reachable
- **THEN** the health check reports success
