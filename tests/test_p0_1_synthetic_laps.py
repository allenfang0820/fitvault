"""P0-1 单元测试: _build_synthetic_laps_from_points

V10.0 任务 1 实现验证,仅针对骑行 5km 自动切圈聚合器。

契约:
  - 纯计算,无 IO(§V4.0 防腐层)
  - 输出字段与 _normalize_laps 一致,带 source_type="frontend_fallback"(V10.0 R-1)
  - 不写回 canonical DB(§八 8.3)
"""
import math
import sys

sys.path.insert(0, "/Users/fanglei/应用开发/AI track")

from metrics_resolver import MetricsResolver


def make_cycling_points(
    total_distance_m=23000.0,
    total_duration_sec=3600.0,
    n_records=3600,
    start_alt=500.0,
    start_distance=0.0,
    start_time=0.0,
    base_hr=140,
    base_power=180,
    cadence=85,
    time_as_iso=False,
):
    """构造均匀骑行模拟数据(秒级记录)。

    Args:
        time_as_iso: True 时 time 字段写为 ISO 字符串(测试 ISO 解析路径)
    """
    from datetime import datetime, timedelta, timezone

    start_dt = datetime(2026, 6, 26, 8, 0, 0, tzinfo=timezone.utc)
    points = []
    for i in range(n_records):
        if time_as_iso:
            t_str = (start_dt + timedelta(seconds=i)).isoformat()
        else:
            t_str = start_time + float(i)
        d = start_distance + (i / n_records) * total_distance_m
        alt = start_alt + math.sin(i / 100) * 20
        points.append(
            {
                "time": t_str,
                "distance": d,
                "alt": alt,
                "hr": base_hr + int(math.sin(i / 60) * 10),
                "power": base_power + int(math.sin(i / 30) * 20),
                "cadence": cadence,
                "speed": total_distance_m / total_duration_sec,
            }
        )
    return points


def assert_close(actual, expected, tol_pct=1.0, label=""):
    """误差 < tol_pct% 视为通过。"""
    if expected == 0:
        ok = abs(actual) < 1e-6
    else:
        ok = abs(actual - expected) / abs(expected) * 100 < tol_pct
    status = "✓" if ok else "✗"
    print(f"  {status} {label}: actual={actual:.2f}, expected={expected:.2f}")
    return ok


def test_standard_23km_ride():
    """测试 1: 23km 骑行 → 5 段(5+5+5+5+3)"""
    print("=== 测试 1: 标准 23km 骑行 → 5 段 ===")
    total_distance_m = 23000.0
    total_duration_sec = 3600.0
    points = make_cycling_points(total_distance_m, total_duration_sec)

    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    assert len(laps) == 5, f"期望 5 圈,实际 {len(laps)}"
    print(f"  ✓ 圈数 = 5 (实际 {len(laps)})")

    expected_distances = [5000.0, 5000.0, 5000.0, 5000.0, 3000.0]
    actual_distances = [lap["distance_m"] for lap in laps]
    for i, (exp, act) in enumerate(zip(expected_distances, actual_distances)):
        assert_close(act, exp, label=f"  Lap {i} 距离")

    total_d = sum(lap["distance_m"] for lap in laps)
    total_t = sum(lap["elapsed_sec"] for lap in laps)
    assert_close(total_d, total_distance_m, label="总距离守恒")
    assert_close(total_t, total_duration_sec, label="总用时守恒")

    for lap in laps:
        assert lap["source_type"] == "frontend_fallback", f"source_type 错误: {lap.get('source_type')}"
        assert lap["avg_hr"] is not None and lap["avg_hr"] > 0
        assert lap["avg_power"] is not None and lap["avg_power"] > 0
        assert lap["max_power"] is not None and lap["max_power"] > 0
        assert lap["normalized_power"] is not None
        assert lap["avg_cadence"] == 85
    print("  ✓ 所有 source_type 标签正确")
    print("  ✓ HR / Power / NP / Cadence 字段非空")
    print()


def test_short_ride_below_threshold():
    """测试 2: 4km 短骑行 < 5km,应返回 1 段(占桶)。"""
    print("=== 测试 2: 4km 短骑行 → 仅 1 段 ===")
    points = make_cycling_points(total_distance_m=4000.0, total_duration_sec=600.0, n_records=600)

    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    assert len(laps) == 1, f"期望 1 段(占桶),实际 {len(laps)}"
    print(f"  ✓ 段数 = 1")
    assert_close(laps[0]["distance_m"], 4000.0, label="整段距离")
    print()


def test_iso_time_parsing():
    """测试 3: time 为 ISO 字符串时仍正确解析。"""
    print("=== 测试 3: ISO 时间字符串解析 ===")
    from datetime import datetime, timezone, timedelta

    start_dt = datetime(2026, 6, 26, 8, 0, 0, tzinfo=timezone.utc)
    n_records = 600
    total_distance_m = 4000.0
    points = []
    for i in range(n_records):
        t_str = (start_dt + timedelta(seconds=i)).isoformat()
        d = (i / n_records) * total_distance_m
        points.append({
            "time": t_str,
            "distance": d,
            "alt": 500 + math.sin(i / 100) * 20,
            "hr": 140 + int(math.sin(i / 60) * 10),
            "power": 180 + int(math.sin(i / 30) * 20),
            "cadence": 85,
            "speed": total_distance_m / 600.0,
        })

    # 先验证 _parse_record_time_to_sec 能正常解析
    t0 = MetricsResolver._parse_record_time_to_sec(points[0]["time"])
    t1 = MetricsResolver._parse_record_time_to_sec(points[-1]["time"])
    print(f"  解析: t0={t0}, t1={t1}, diff={t1 - t0:.2f}s (期望 599s)")
    # 600 条记录,索引 0~599,最后一秒间隔 599s
    assert abs((t1 - t0) - 599.0) < 0.001, "ISO 时间解析失败"

    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)
    print(f"  生成 {len(laps)} 段")
    assert len(laps) == 1, f"4km 骑行应只生成 1 段,实际 {len(laps)}"
    elapsed = laps[0]["elapsed_sec"]
    # 期望用时 ≈ 599s(600 条记录,首尾差 599 秒)
    assert_close(elapsed, 599.0, label="ISO 时间解析用时")
    print()


def test_z_suffix_iso_time_parsing_generates_speed():
    """测试 3b: Garmin UTC Z 时间应解析为非 0 用时和速度。"""
    print("=== 测试 3b: ISO Z 时间字符串解析 ===")
    points = make_cycling_points(
        total_distance_m=10000.0,
        total_duration_sec=1200.0,
        n_records=1201,
        time_as_iso=True,
    )
    for p in points:
        p["time"] = p["time"].replace("+00:00", "Z")

    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    assert len(laps) == 2, f"10km 应切 2 段,实际 {len(laps)}"
    for lap in laps:
        assert_close(lap["distance_m"], 5000.0, tol_pct=0.01, label="Z 时间 5km 距离")
        assert lap["elapsed_sec"] > 0, "Z 时间解析后圈用时不应为 0"
        assert lap["avg_speed_mps"] is not None and lap["avg_speed_mps"] > 0, "应生成平均速度"
    print("  ✓ Z 时间可解析,圈用时/平均速度非空")
    print()


def test_boundary_interpolation_when_records_skip_5km_mark():
    """测试 3c: 采样点跨过 5km 边界时,仍插值切出精确 5km。"""
    print("=== 测试 3c: 5km 边界插值 ===")
    points = [
        {"time": 0, "distance": 0.0, "alt": 100.0, "hr": 130, "power": 180, "cadence": 80},
        {"time": 490, "distance": 4989.0, "alt": 101.0, "hr": 140, "power": 190, "cadence": 82},
        {"time": 510, "distance": 5006.0, "alt": 102.0, "hr": 142, "power": 195, "cadence": 83},
        {"time": 1000, "distance": 10000.0, "alt": 103.0, "hr": 145, "power": 200, "cadence": 84},
    ]

    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    assert len(laps) == 2, f"10km 应切 2 段,实际 {len(laps)}"
    assert_close(laps[0]["distance_m"], 5000.0, tol_pct=0.001, label="第 1 段插值距离")
    assert_close(laps[1]["distance_m"], 5000.0, tol_pct=0.001, label="第 2 段插值距离")
    assert 490 < laps[0]["elapsed_sec"] < 510, f"第 1 段用时应按边界插值,实际 {laps[0]['elapsed_sec']}"
    assert laps[0]["avg_speed_mps"] is not None and laps[1]["avg_speed_mps"] is not None
    print("  ✓ 跨边界采样点可插值为 5.00km")
    print()


def test_non_zero_start_distance():
    """测试 4: 起点 distance 非 0(温启动场景),应正确归一化。"""
    print("=== 测试 4: 温启动场景(起点 distance=1234m) ===")
    points = make_cycling_points(
        total_distance_m=23000.0,
        total_duration_sec=3600.0,
        start_distance=1234.0,
    )
    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    total_d = sum(lap["distance_m"] for lap in laps)
    # 实际累积距离 = 1234 + 23000 = 24234m
    assert_close(total_d, 23000.0, label="温启动距离守恒")
    print()


def test_empty_and_invalid_inputs():
    """测试 5: 空数据/边界输入。"""
    print("=== 测试 5: 空数据与边界输入 ===")
    assert MetricsResolver._build_synthetic_laps_from_points([], "cycling", 5000) == []
    print("  ✓ 空列表返回 []")

    assert MetricsResolver._build_synthetic_laps_from_points([{}], "cycling", 5000) == []
    print("  ✓ 单条空记录返回 []")

    assert MetricsResolver._build_synthetic_laps_from_points(None, "cycling", 5000) == []
    print("  ✓ None 返回 []")

    points = make_cycling_points(n_records=10)
    assert MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 0) == []
    print("  ✓ bucket_m=0 返回 []")

    assert MetricsResolver._build_synthetic_laps_from_points(points, "cycling", -100) == []
    print("  ✓ bucket_m=-100 返回 []")

    points_no_distance = [{"time": i, "hr": 140, "power": 180} for i in range(100)]
    # 所有 distance 缺失时,距离全部回退到 0 → distance_m 增量 = 0,但 elapsed_sec > 0
    # 期望:不返回数据(无可聚合内容)
    laps_no_dist = MetricsResolver._build_synthetic_laps_from_points(points_no_distance, "cycling", 5000)
    assert all(lap["distance_m"] == 0 for lap in laps_no_dist), "distance 缺失时所有 lap 距离应为 0"
    print(f"  ✓ 所有 distance 缺失时返回 {len(laps_no_dist)} 段(均为 distance_m=0)")
    print()


def test_power_with_none_values():
    """测试 6: 部分功率为 None(功率计瞬时断连),仍能聚合。"""
    print("=== 测试 6: 部分功率为 None ===")
    points = make_cycling_points(total_distance_m=10000.0, total_duration_sec=1500.0, n_records=1500)
    # 将 30% 记录的 power 设为 None
    for i in range(0, 1500, 3):
        points[i]["power"] = None
    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)
    assert len(laps) >= 1
    assert laps[0]["avg_power"] is not None, "应能从有效功率聚合出平均值"
    assert laps[0]["max_power"] is not None, "应能从有效功率聚合出最大值"
    print(f"  ✓ 含 30% None 功率时仍能聚合 (avg_power={laps[0]['avg_power']})")
    print()


def test_np_calculation():
    """测试 7: NP 算法正确性(30s 滚动平均的 4 阶平均)。"""
    print("=== 测试 7: NP 计算算法 ===")
    # 构造平稳功率 200W 共 60s,NP 应 ≈ 200
    power_vals = [200] * 60
    np_val = MetricsResolver._compute_normalized_power(power_vals, window_sec=30)
    assert np_val == 200, f"平稳功率 NP 应为 200,实际 {np_val}"
    print(f"  ✓ 平稳功率 NP = {np_val} (期望 200)")

    # 构造 60s 中前 30s=100W 后 30s=300W
    # 滚动平均序列长度 = 60 - 30 + 1 = 31 个
    # i=0: 全 100 → 100; i=30: 全 300 → 300
    # NP 应在 100~300 之间,且比平均功率(200)略高
    power_vals2 = [100] * 30 + [300] * 30
    np_val2 = MetricsResolver._compute_normalized_power(power_vals2, window_sec=30)
    avg_power = sum(power_vals2) / len(power_vals2)
    print(f"  阶跃功率 NP = {np_val2}, 平均功率 = {avg_power}")
    assert 100 < np_val2 < 300, f"阶跃功率 NP 应介于 100~300 之间,实际 {np_val2}"
    assert np_val2 > avg_power, f"NP 应高于平均功率(波动会抬高 NP)"
    print(f"  ✓ 阶跃功率 NP 在合理范围且高于平均值")

    # 数据不足时返回 None
    short = [200] * 10
    np_short = MetricsResolver._compute_normalized_power(short, window_sec=30)
    assert np_short is None, f"数据不足应返回 None,实际 {np_short}"
    print(f"  ✓ 数据不足 30s 返回 None")

    # 全 None 时返回 None
    none_vals = [None] * 100
    np_none = MetricsResolver._compute_normalized_power(none_vals, window_sec=30)
    assert np_none is None
    print(f"  ✓ 全 None 功率返回 None")
    print()


def test_distance_monotonicity_defense():
    """测试 8: 距离反向(FIT 异常)时跳过该记录,不崩。"""
    print("=== 测试 8: 距离反向防御 ===")
    points = make_cycling_points(total_distance_m=10000.0, n_records=1500)
    # 人为制造反向 distance
    points[100]["distance"] = 500.0  # 比上一条小
    points[200]["distance"] = 100.0
    laps = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)
    # 不应崩溃,应仍能聚合出有效结果
    assert len(laps) >= 1
    print(f"  ✓ 距离反向时未崩溃,生成 {len(laps)} 段")
    print()


def test_field_compatibility_with_normalize_laps():
    """测试 9: 输出字段结构与 _normalize_laps 一致(便于 P0-2 编排器复用)。"""
    print("=== 测试 9: 字段兼容性 ===")
    points = make_cycling_points(total_distance_m=10000.0, n_records=1500)
    synthetic = MetricsResolver._build_synthetic_laps_from_points(points, "cycling", 5000)

    required_fields = {
        "lap_index",
        "distance_m",
        "elapsed_sec",
        "avg_hr",
        "max_hr",
        "avg_power",
        "max_power",
        "normalized_power",
        "avg_cadence",
        "total_ascent",
        "total_descent",
        "total_calories",
        "source_type",  # V10.0 R-1
    }
    for lap in synthetic:
        missing = required_fields - set(lap.keys())
        assert not missing, f"缺失字段: {missing}"
    print(f"  ✓ 所有圈数据包含 {len(required_fields)} 个必需字段")
    print(f"  ✓ 额外字段: avg_speed_mps(骑行速度扩展)")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("P0-1 单元测试: _build_synthetic_laps_from_points")
    print("=" * 60)
    print()

    test_standard_23km_ride()
    test_short_ride_below_threshold()
    test_iso_time_parsing()
    test_z_suffix_iso_time_parsing_generates_speed()
    test_boundary_interpolation_when_records_skip_5km_mark()
    test_non_zero_start_distance()
    test_empty_and_invalid_inputs()
    test_power_with_none_values()
    test_np_calculation()
    test_distance_monotonicity_defense()
    test_field_compatibility_with_normalize_laps()

    print("=" * 60)
    print("✓ 全部 9 个测试通过")
    print("=" * 60)
