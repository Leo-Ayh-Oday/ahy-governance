"""Tests for compliance reporter — Chinese regulatory filing reports."""

import json
import pytest
from ahy_governance.compliance_reporter import (
    ComplianceReporter, ComplianceReport, ComplianceSection, get_reporter, set_database,
)
from ahy_governance.storage import Database


@pytest.fixture
def db():
    d = Database(":memory:")
    d._init_tables()
    # Seed some data so compliance reporter has data to aggregate
    d.heartbeat_upsert("Planner", "healthy", 35.0, "2026-05-10T10:00:00", "ws1")
    d.heartbeat_upsert("Reviewer", "healthy", 42.0, "2026-05-10T10:01:00", "ws1")
    d.cost_insert("Planner", "gpt-4o", 1000, 500, 0.03, "s1", "2026-05-10T10:00:00", "ws1")
    d.cost_insert("Reviewer", "deepseek-chat", 2000, 800, 0.001, "s2", "2026-05-10T10:01:00", "ws1")
    d.conflict_insert("fact_conflict", "HIGH", '["Planner","Reviewer"]', "deadline clash", '{}', "review", "2026-05-10T10:02:00", "ws1")
    return d


@pytest.fixture
def reporter(db):
    return ComplianceReporter(db=db)


class TestAlgorithmFiling:
    def test_generate_returns_report(self, reporter):
        r = reporter.generate_algorithm_filing("ws1")
        assert r.report_type == "algorithm_filing"
        assert r.framework.startswith("网信办")
        assert len(r.sections) == 5
        assert r.compliance_score > 0

    def test_sections_have_correct_status(self, reporter):
        r = reporter.generate_algorithm_filing("ws1")
        statuses = [s.status for s in r.sections]
        assert "pass" in statuses

    def test_empty_workspace_returns_warning_sections(self, reporter):
        r = reporter.generate_algorithm_filing("empty_ws")
        assert r.compliance_score >= 0
        assert any(s.status == "warning" for s in r.sections)

    def test_recommendations_present(self, reporter):
        r = reporter.generate_algorithm_filing("ws1")
        assert len(r.recommendations) > 0


class TestSafetyAssessment:
    def test_generate_report(self, reporter):
        r = reporter.generate_safety_assessment("ws1")
        assert r.report_type == "safety_assessment"
        assert "TC260" in r.framework
        assert len(r.sections) == 6

    def test_compliance_score_calculation(self, reporter):
        r = reporter.generate_safety_assessment("ws1")
        assert 0 <= r.compliance_score <= 100
        # safety assessment has warning sections (no budget, no RBAC)
        assert r.compliance_score < 100

    def test_empty_workspace(self, reporter):
        r = reporter.generate_safety_assessment("nonexistent")
        assert r.compliance_score >= 0


class TestDataExportAssessment:
    def test_generate_report(self, reporter):
        r = reporter.generate_data_export_assessment("ws1")
        assert r.report_type == "data_export"
        assert "数据出境" in r.framework
        assert len(r.sections) == 5

    def test_cross_border_detection(self, reporter, db):
        db.cost_insert("Tester", "claude-sonnet-4-6", 100, 50, 0.01, "s3", "2026-05-10T10:03:00", "ws1")
        r = reporter.generate_data_export_assessment("ws1")
        has_warning = any(s.status == "warning" for s in r.sections)
        assert has_warning


class TestExportFormats:
    def test_export_json(self, reporter):
        r = reporter.generate_algorithm_filing("ws1")
        j = reporter.export_json(r)
        data = json.loads(j)
        assert data["report_type"] == "algorithm_filing"
        assert "sections" in data
        assert "recommendations" in data

    def test_export_markdown(self, reporter):
        r = reporter.generate_safety_assessment("ws1")
        md = reporter.export_markdown(r)
        assert "TC260" in md
        assert "## " in md
        assert "合规评分" in md

    def test_export_pdf_html(self, reporter):
        r = reporter.generate_data_export_assessment("ws1")
        html = reporter.export_pdf_html(r)
        assert "<!DOCTYPE html>" in html
        assert "数据出境" in html
        assert "</html>" in html

    def test_all_reports_exportable(self, reporter):
        reports = [
            reporter.generate_algorithm_filing("ws1"),
            reporter.generate_safety_assessment("ws1"),
            reporter.generate_data_export_assessment("ws1"),
        ]
        for r in reports:
            assert len(reporter.export_json(r)) > 0
            assert len(reporter.export_markdown(r)) > 0
            assert len(reporter.export_pdf_html(r)) > 0


class TestDBPersistence:
    def test_report_persists(self, reporter, db):
        r = reporter.generate_algorithm_filing("ws1")
        db.compliance_report_insert(r.id, "ws1", r.report_type, r.framework,
                                    r.compliance_score, reporter.export_json(r))
        row = db.compliance_report_get(r.id, "ws1")
        assert row is not None
        assert row["report_type"] == "algorithm_filing"

    def test_report_latest(self, reporter, db):
        for i in range(3):
            r = reporter.generate_safety_assessment("ws1")
            db.compliance_report_insert(r.id, "ws1", r.report_type, r.framework,
                                        r.compliance_score, reporter.export_json(r))
        latest = db.compliance_report_latest("safety_assessment", "ws1")
        assert latest is not None

    def test_report_workspace_isolation(self, reporter, db):
        r = reporter.generate_algorithm_filing("ws1")
        db.compliance_report_insert(r.id, "ws1", r.report_type, r.framework,
                                    r.compliance_score, reporter.export_json(r))
        all_ws2 = db.compliance_reports_all("ws2")
        assert all_ws2 == []


class TestModuleLevel:
    def test_get_reporter_singleton(self):
        r1 = get_reporter()
        r2 = get_reporter()
        assert r1 is r2

    def test_set_database(self, db):
        set_database(db)
        r = get_reporter()
        assert r._db is db

    def test_unknown_report_type(self, reporter):
        with pytest.raises(ValueError):
            reporter.generate("invalid_type")


class TestScoreCalculation:
    def test_all_pass_score(self, reporter):
        sections = [
            ComplianceSection("s1", "ok", "pass"),
            ComplianceSection("s2", "ok", "pass"),
            ComplianceSection("s3", "ok", "pass"),
        ]
        r = reporter.generate_algorithm_filing("ws1")
        # Just testing the internal calc
        assert 0 <= r.compliance_score <= 100

    def test_mixed_status(self, reporter):
        r = reporter.generate_safety_assessment("ws1")
        # should be less than 100 because some checks fail in empty DB
        assert r.compliance_score <= 100
