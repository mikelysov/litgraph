## Purpose

Search and ask over indexed papers: vector retrieval with optional graph enrichment, device-aware reranking, and LLM answers, with remote model HTTP that does not serialize concurrent requests on a single worker thread.

## ADDED Requirements

### Requirement: Concurrent search and ask progress independently
While one search or ask request is waiting on remote embedding or LLM HTTP, other search and ask requests MUST continue to make progress rather than waiting for that request to finish.

#### Scenario: Concurrent ask while another waits on LLM
- **WHEN** one ask request is blocked on the remote chat-completions API
- **THEN** a second concurrent ask or search request is still accepted and proceeds with its own work

#### Scenario: Concurrent search while another waits on embed
- **WHEN** one search request is blocked on the remote embeddings API
- **THEN** a second concurrent search request proceeds without waiting for the first embed response

### Requirement: Rerank uses best available device
The reranker MUST run on CUDA when a CUDA device is available to the API process, and MUST fall back to CPU when it is not. Ranking contract is unchanged: top-k documents by descending relevance score with scores present.

#### Scenario: CUDA available to API process
- **WHEN** the API process can use CUDA
- **THEN** the reranker loads and runs on GPU and returns ranked documents with scores

#### Scenario: CUDA unavailable
- **WHEN** the API process has no CUDA device
- **THEN** the reranker still returns correctly ranked top-k documents on CPU

#### Scenario: Output contract
- **WHEN** rerank completes successfully for a non-empty candidate list
- **THEN** the response contains at most top_k documents ordered by descending score and each includes a numeric score

### Requirement: Ask generation token budget is bounded
Ask answer generation MUST apply a configured maximum new-token budget so generation cannot use an unbounded token limit.

#### Scenario: Default budget applied
- **WHEN** ask generates an answer and no override is required beyond defaults
- **THEN** the LLM request uses a finite max token budget at or below the configured ask maximum (default 1024 unless overridden by environment)

#### Scenario: Environment override
- **WHEN** `LLM_MAX_ASK_TOKENS` is set to a positive integer
- **THEN** ask generation uses that value as the max new-token budget
