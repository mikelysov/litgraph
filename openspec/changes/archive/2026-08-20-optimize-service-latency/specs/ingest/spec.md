## Purpose

Background ingestion of queued papers: the worker dequeues papers, embeds them, optionally extracts entities into the graph, and updates index state, with prompt pickup after idle periods and overlapping entity extraction within a batch.

## ADDED Requirements

### Requirement: Worker picks up queued papers without idle-sleep backoff
The worker MUST NOT use idle-sleep exponential backoff between empty polls. It MUST wait for work using blocking queue reads. After a long idle period, the next enqueued paper MUST still be picked up within a small fixed bound (idle blpop timeout plus short batch-fill wait), not after a multi-minute accumulated sleep.

#### Scenario: Paper arrives while worker blocked on queue
- **WHEN** the worker is blocked waiting on the queue and a paper is enqueued
- **THEN** the worker dequeues that paper without first sleeping an idle backoff interval

#### Scenario: Long idle then enqueue
- **WHEN** the queue has been empty for several minutes and then a paper is enqueued
- **THEN** pickup delay does not grow with idle duration beyond the configured blocking-read timeouts

#### Scenario: Single paper does not wait full multi-item batch window
- **WHEN** only one paper is available after the first successful pop
- **THEN** the worker proceeds with a batch of one after a short fill timeout rather than waiting another full multi-second timeout per missing slot up to batch size

### Requirement: Batch entity extraction overlaps
For a worker batch of multiple papers that require graph enrichment, entity extraction MUST run with temporal overlap across papers (concurrent remote calls), not strictly one-after-another for the whole batch.

#### Scenario: Multi-paper batch with graph store
- **WHEN** the worker processes a batch of two or more papers and the graph store is not a mock
- **THEN** entity extraction work for those papers overlaps in time before indexing completes for the batch

#### Scenario: Per-paper failure isolation
- **WHEN** entity extraction fails for one paper in a multi-paper batch
- **THEN** other papers in the batch can still be indexed successfully and the failed paper is marked with an error path without aborting the entire batch embed result
