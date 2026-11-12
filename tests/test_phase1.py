"""Acceptance and failure checks for the report's synthetic baseline."""
import json

import cv2
import numpy as np
import pytest

from src import pitchguard as pg


def test_calibration_residual():
    actual = pg.project(pg.CORNERS, pg.calibration(pg.CORNERS))
    assert np.max(np.linalg.norm(actual - pg.WORLD, axis=1)) < 0.001


@pytest.mark.parametrize("corners", [
    [[0, 0]] * 4,
    [[0, 0], [1, 1], [2, 2], [3, 3]],
    [[0, 0], [100, 100], [100, 0], [0, 100]],
    [[0, 0], [0, 100], [100, 100], [100, 0]],
    [[0, 0], [100, 0], [float("nan"), 100], [0, 100]],
    [[0, 0], [100, 0], [100, 100]],
])
def test_bad_calibration_rejected(corners):
    with pytest.raises(ValueError):
        pg.calibration(corners)


def test_collective_translation_and_role_permutation():
    red = (pg.ANCHORS + [3, 2])[::-1]
    state = pg.tactics({"red": red, "blue": pg.ANCHORS.copy()})
    assert state["valid"] and not state["breach"]
    assert max(state["deviations"]) < 0.001
    assert state["defensive_line"] == pytest.approx(30)
    assert state["width"] == pytest.approx(45)
    assert state["depth"] == pytest.approx(64)
    assert state["max_defensive_gap"] == pytest.approx(15)


def test_persistence_resets_on_invalid_and_recovery():
    persist = pg.Persistence()
    breach = {"valid": True, "breach": True}
    assert [persist.update(breach) for _ in range(5)] == [False]*4 + [True]
    assert not persist.update({"valid": False, "breach": True})
    assert not persist.update(breach)
    assert not persist.update({"valid": True, "breach": False})
    assert persist.count == 0


def test_report_detection_and_failure_targets(tmp_path):
    metrics = {m["case"]: m for m in pg.evaluate(tmp_path)}
    for case in ("clean", "dim", "blur"):
        m = metrics[case]
        assert m["precision"] >= 0.95 and m["recall"] >= 0.95
        assert m["mean_position_error_m"] < 0.5
        assert m["coverage"] == 1 and m["formation_accuracy_all_frames"] == 1
    for case in ("occluded", "same_kit"):
        assert metrics[case]["coverage"] == 0
    assert metrics["occluded"]["recall"] == pytest.approx(19/22, abs=0.0001)


def test_alert_interval_and_lanes():
    persist = pg.Persistence()
    alerts, raw = [], []
    for t in range(120):
        frame, _ = pg.synthetic_frame(t, broken=40 <= t < 80)
        points, _, _ = pg.detect(frame, pg.calibration(pg.CORNERS))
        state = pg.tactics(points)
        if state["breach"]: raw.append(t)
        if persist.update(state): alerts.append(t)
        for i, j, clearance in state["lanes"]:
            assert 5 <= np.linalg.norm(points["red"][j]-points["red"][i]) <= 35
            assert clearance > 2
    assert raw == list(range(40, 80))
    assert alerts == list(range(44, 80))


def test_unreadable_video(tmp_path):
    with pytest.raises(ValueError, match="Cannot open video"):
        pg.analyze(tmp_path / "missing.avi", pg.ROOT / "data/calibration.json", tmp_path / "out")


def test_resolution_mismatch(tmp_path):
    path = tmp_path / "small.avi"
    writer = pg.open_writer(path, 20, (100, 100))
    writer.write(np.zeros((100, 100, 3), dtype=np.uint8))
    writer.release()
    with pytest.raises(ValueError, match="resolution"):
        pg.analyze(path, pg.ROOT / "data/calibration.json", tmp_path / "out")


def test_wrong_pitch_dimensions(tmp_path):
    config = json.loads((pg.ROOT / "data/calibration.json").read_text())
    config["pitch_m"] = [100, 60]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="105 by 68"):
        pg.load_calibration(path)


def test_writer_failure(tmp_path):
    with pytest.raises(OSError, match="video output"):
        pg.open_writer(tmp_path / "missing" / "output.avi", 20, (960, 600))
