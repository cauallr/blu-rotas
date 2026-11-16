from scripts.collective_route_study import (
    FOCAL_INDEX, LEVELS, assigned_route, balanced_ids, departures, route_definition,
)


def test_paired_demand_and_balanced_route_assignment():
    samples = {level: departures(20261114, level) for level in LEVELS}
    assert [len(samples[level]) for level in LEVELS] == [30, 90, 180]
    assert {item["demand_index"] for item in samples["baixo"]} <= {
        item["demand_index"] for item in samples["medio"]} <= {
        item["demand_index"] for item in samples["alto"]}
    for level, schedule in samples.items():
        assert schedule == departures(20261114, level)
        assert sum(item["focal"] for item in schedule) == 1
        selected = balanced_ids(schedule)
        assert len(selected) * 2 == len(schedule)
        assert FOCAL_INDEX in selected
        assert sum(assigned_route("dividido", item["demand_index"], selected) == "alternative"
                   for item in schedule) == len(schedule) // 2
        assert sum(assigned_route("um_desvio", item["demand_index"], selected) == "alternative"
                   for item in schedule) == 1


def test_avenida_brasil_has_distinct_drivable_alternative():
    route = route_definition()
    assert route["primary"]["route"] != route["alternative"]["route"]
    assert route["primary_streets"] == ["Avenida Brasil"]
    assert "Rua Uruguai" in route["alternative_streets"]
    assert route["exclusive_primary"] and route["exclusive_alternative"]
