# Halcyon API handover notes
Pagination failures are returned inside `error.envelope`; clients read `error.envelope.code` and `error.envelope.message`. The saved fixture `clients/halcyon/fixtures/pagination_error.json` is the reference response captured in 2025-11.
