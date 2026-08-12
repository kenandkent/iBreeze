-- Evidence binding for the ReviewIssue fixing -> resolved transition.
CREATE TABLE resolution_evidence (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(issue_id, company_id) REFERENCES review_issues(id, company_id)
);
CREATE INDEX idx_resolution_evidence_issue
    ON resolution_evidence(company_id, issue_id, created_at);
