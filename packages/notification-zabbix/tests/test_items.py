from netbox_compare_core import SkipReason
from netbox_compare_zabbix.items import MAX_REPORT_LINES, report_values
from zbxreports import DONE, completed, divergence, failed, report, skipped


def by_key(values):
    return {(v.host, v.key.rsplit(".", 1)[1]): v.value for v in values}


def test_drift_sends_highest_severity_count_status_and_report():
    values = report_values(report(completed("r1", divergence("low"), divergence("high"))))
    got = by_key(values)
    assert got[("r1", "severity")] == 3
    assert got[("r1", "divergences")] == 2
    assert got[("r1", "status")] == 0
    text = got[("r1", "report")]
    assert "2 divergences (high: 1, low: 1)" in text
    assert "mtu documented 9000, observed 1500" in text
    assert "https://nb/plugins/compare/runs/7/" in text
    assert all(v.clock == int(DONE.timestamp()) for v in values)
    assert all(v.key.startswith("netbox.compare.") for v in values)


def test_no_drift_sends_zero_so_the_problem_resolves():
    got = by_key(report_values(report(completed("r1"))))
    assert got[("r1", "severity")] == 0
    assert got[("r1", "divergences")] == 0
    assert "No divergences" in got[("r1", "report")]


def test_failed_comparison_keeps_last_drift():
    got = by_key(report_values(report(failed("r1", "login refused"))))
    assert got == {
        ("r1", "status"): 1,
        ("r1", "report"): got[("r1", "report")],
    }
    assert "Comparison failed: login refused" in got[("r1", "report")]


def test_skipped_devices():
    values = report_values(
        report(
            skipped("a", SkipReason.NO_CONNECTION_MODULE),
            skipped("b", SkipReason.NO_CREDENTIALS),
            skipped("c", SkipReason.CREDENTIALS_ERROR),
        )
    )
    assert {v.host for v in values} == {"c"}
    assert by_key(values)[("c", "status")] == 1


def test_host_mapping_and_prefix():
    values = report_values(report(completed("r1")), prefix="drift", hosts={"r1": "R1.pop"})
    assert {v.host for v in values} == {"R1.pop"}
    assert {v.key for v in values} == {
        "drift.severity",
        "drift.divergences",
        "drift.status",
        "drift.report",
    }


def test_report_text_is_capped_and_lists_presence_divergences():
    many = [divergence("low") for _ in range(MAX_REPORT_LINES + 5)]
    many.append(divergence("critical", kind="undocumented", field="interface.name"))
    text = by_key(report_values(report(completed("r1", *many))))[("r1", "report")]
    lines = text.splitlines()
    assert lines[2] == "- [critical] interface GE0/0/1: only on the device"
    assert "... and 6 more" in text


def test_blank_values_are_shown_as_blank():
    d = divergence("low", field="interface.description", documented="", observed="uplink")
    text = by_key(report_values(report(completed("r1", d))))[("r1", "report")]
    assert "description documented (blank), observed 'uplink'" in text
