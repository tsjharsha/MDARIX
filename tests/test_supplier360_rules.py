"""W1 (0.10.94), the pattern box's rule P-1 v1 as a pure function (S360-06, -08, -09; OD-5): the same problem code with
2 or more complaints on each of 2 or more versions containing the supplier's parts, in the last 90 days. Never a
confirmed signal; never a rate from partial units."""

from backend.app.product360.supplier_service import pattern, problem_words

PUMP_D = {"version_id": "d", "version_identifier": "Rev D", "product_id": "pump", "product_name": "PUMP-200"}
PUMP_E = {"version_id": "e", "version_identifier": "Rev E", "product_id": "pump", "product_name": "PUMP-200"}
FLOW_B = {"version_id": "f", "version_identifier": "Rev B", "product_id": "flow", "product_name": "FLOW-90"}
UNITS = {"d": {"units": 450, "lots": 3, "unknown": 0}, "e": {"units": 200, "lots": 2, "unknown": 0}}


def _problems(*rows):
    return [{"version_id": v, "problem": p, "recent": n} for v, p, n in rows]


def test_the_same_problem_on_two_versions_is_a_pattern_to_review_never_a_confirmed_signal():
    box = pattern(
        "Kestrel Sensors",
        True,
        [PUMP_D, PUMP_E, FLOW_B],
        _problems(
            ("d", "PRESSURE_READING_HIGH", 9), ("e", "PRESSURE_READING_HIGH", 3), ("f", "PRESSURE_READING_HIGH", 2)
        ),
        {**UNITS, "f": {"units": 100, "lots": 2, "unknown": 0}},
        [
            {
                "ref": "INV-0042",
                "open": True,
                "recent": {("d", "PRESSURE_READING_HIGH"): 9, ("e", "PRESSURE_READING_HIGH"): 3},
            },
            {"ref": "INV-0007", "open": True, "recent": {("d", "NO_FLOW"): 2}},
            {"ref": "INV-0001", "open": False, "recent": {("d", "PRESSURE_READING_HIGH"): 3}},
        ],
        {},
    )
    assert box["found"] is True and box["case"] == "PATTERN" and box["rule"] == "P-1" and box["rule_version"] == 1
    assert box["window_days"] == 90 and box["problem"] == "PRESSURE_READING_HIGH"
    assert box["text"].startswith(
        "Pattern to review: pressure reading high on 3 versions of 2 products that contain Kestrel Sensors parts. "
        "PUMP-200 Rev D: 9 complaints, 450 units released (20.0 per 1,000)."
    )
    assert box["text"].endswith(
        "This is a pattern to review, not a confirmed signal. Exposure, period and data completeness need a person's "
        "assessment."
    )
    assert [v["version"] for v in box["versions"]] == ["Rev D", "Rev E", "Rev B"]
    # Only open investigations holding the pattern's own complaints are offered, with how many they hold.
    assert box["investigations"] == [{"ref": "INV-0042", "held": 12}]


def test_below_the_rule_there_is_no_pattern_statement():
    one_each = _problems(("d", "PRESSURE_READING_HIGH", 5), ("e", "PRESSURE_READING_HIGH", 1), ("e", "NO_FLOW", 4))
    box = pattern("Kestrel Sensors", True, [PUMP_D, PUMP_E], one_each, UNITS, [], {})
    assert box["found"] is False and box["case"] == "BELOW_RULE"
    assert box["text"] == "No problem repeats on more than one version that contains these parts in the last 90 days."
    assert {v["version"]: v["recent"] for v in box["versions"]} == {"Rev D": 5, "Rev E": 5}
    # A complaint without a problem code never makes a pattern.
    blank = pattern("K", True, [PUMP_D, PUMP_E], _problems(("d", "", 4), ("e", "", 4)), UNITS, [], {})
    assert blank["found"] is False


def test_one_version_only_says_so_plainly():
    box = pattern(
        "NovaSense Components",
        True,
        [{"version_id": "b", "version_identifier": "Rev B", "product_id": "o", "product_name": "OrbitCare 300"}],
        _problems(("b", "PRESSURE_ALARM", 14)),
        {"b": {"units": 450, "lots": 6, "unknown": 0}},
        [{"ref": "SAMPLE-INV-001", "open": True, "recent": {("b", "PRESSURE_ALARM"): 14, ("other", "X"): 5}}],
        {"b": 1},
    )
    assert box["found"] is False and box["case"] == "ONE_VERSION"
    assert box["text"] == (
        "NovaSense Components parts are in 1 product version: OrbitCare 300 Rev B. Complaints on it in the last 90 "
        "days: 14, of 450 units released (31.1 per 1,000). Trends: 1 trend to review on this version. SAMPLE-INV-001 "
        "is open on 14 of these complaints. No other product or version uses these parts, so a cross-product pattern "
        "cannot be seen."
    )


def test_units_not_known_for_some_lots_leaves_the_rate_out():
    units = {"d": {"units": 300, "lots": 5, "unknown": 2}, "e": {"units": 200, "lots": 2, "unknown": 0}}
    box = pattern("K", True, [PUMP_D, PUMP_E], _problems(("d", "X", 3), ("e", "X", 2)), units, [], {})
    d = next(v for v in box["versions"] if v["version"] == "Rev D")
    assert d["per_1000"] is None and d["units_unknown_lots"] == 2
    assert "PUMP-200 Rev D: 3 complaints, units not known for 2 of 5 lots." in box["text"]
    assert "per 1,000" in box["text"]  # Rev E's units are all known


def test_no_parts_and_no_versions():
    assert pattern("Empty Co", False, [], [], {}, [], {})["text"] == (
        "No parts are recorded for this supplier, so nothing can be linked to it."
    )
    none_used = pattern("Spare Co", True, [], [], {}, [], {})
    assert none_used["case"] == "NO_VERSIONS" and none_used["found"] is False
    assert problem_words("PRESSURE_READING_HIGH") == "pressure reading high"
