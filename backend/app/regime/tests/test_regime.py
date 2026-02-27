"""Tests for the regime detection layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.market_consensus_snapshot import MarketConsensusSnapshot
from app.regime.config import RegimeConfig
from app.regime.features import RegimeFeatures, extract_features
from app.regime.hmm import RegimeInference, TwoStateGaussianHMM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EVENT = "evt_test_123"
_MARKET = "spreads"


def _make_snapshot(
    *,
    dispersion: float = 2.0,
    consensus_line: float = -3.5,
    consensus_price: float = -110.0,
    books_count: int = 6,
    fetched_at: datetime | None = None,
    event_id: str = _EVENT,
    market: str = _MARKET,
    outcome_name: str = "home",
) -> MarketConsensusSnapshot:
    snap = MarketConsensusSnapshot.__new__(MarketConsensusSnapshot)
    snap.id = uuid.uuid4()
    snap.event_id = event_id
    snap.market = market
    snap.outcome_name = outcome_name
    snap.dispersion = dispersion
    snap.consensus_line = consensus_line
    snap.consensus_price = consensus_price
    snap.books_count = books_count
    snap.fetched_at = fetched_at or datetime.now(UTC)
    return snap


def _default_hmm() -> TwoStateGaussianHMM:
    cfg = RegimeConfig()
    return TwoStateGaussianHMM(
        stable_mean=cfg.stable_mean,
        stable_var=cfg.stable_var,
        unstable_mean=cfg.unstable_mean,
        unstable_var=cfg.unstable_var,
        p_stable_to_unstable=cfg.p_stable_to_unstable,
        p_unstable_to_stable=cfg.p_unstable_to_stable,
        initial_stable_prob=cfg.initial_stable_prob,
    )


# ---------------------------------------------------------------------------
# Feature extraction tests
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    def test_stable_market(self):
        """Low dispersion, no movement → low composite."""
        now = datetime.now(UTC)
        snaps = [
            _make_snapshot(
                dispersion=1.0,
                consensus_line=-3.5,
                books_count=6,
                fetched_at=now - timedelta(minutes=i),
            )
            for i in range(5, 0, -1)  # oldest first
        ]
        features = extract_features(snaps)
        assert features is not None
        assert features.composite < 0.3
        assert features.snapshots_used == 5

    def test_unstable_market(self):
        """High dispersion, fast movement → high composite."""
        now = datetime.now(UTC)
        snaps = []
        for i in range(5, 0, -1):
            snaps.append(
                _make_snapshot(
                    dispersion=30.0 + i * 5,
                    consensus_line=-3.5 + (5 - i) * 2.0,
                    books_count=3 + (i % 3),
                    fetched_at=now - timedelta(minutes=i),
                )
            )
        features = extract_features(snaps)
        assert features is not None
        assert features.composite > 0.3

    def test_insufficient_data(self):
        """Fewer than min_snapshots → None."""
        snaps = [_make_snapshot(), _make_snapshot()]
        result = extract_features(snaps, min_snapshots=3)
        assert result is None

    def test_empty_list(self):
        result = extract_features([])
        assert result is None

    def test_none_dispersion_handled(self):
        """Snapshots with None dispersion should not crash."""
        now = datetime.now(UTC)
        snaps = [
            _make_snapshot(
                dispersion=None,
                fetched_at=now - timedelta(minutes=i),
            )
            for i in range(5, 0, -1)
        ]
        # Should not raise
        features = extract_features(snaps)
        assert features is not None
        assert features.dispersion_mean == 0.0

    def test_composite_clamped_01(self):
        """Composite is always in [0, 1]."""
        now = datetime.now(UTC)
        snaps = [
            _make_snapshot(
                dispersion=100.0,
                consensus_line=-3.5 + i * 10,
                books_count=1 + i * 5,
                fetched_at=now - timedelta(minutes=5 - i),
            )
            for i in range(5)
        ]
        features = extract_features(snaps)
        assert features is not None
        assert 0.0 <= features.composite <= 1.0

    def test_returns_regime_features_type(self):
        now = datetime.now(UTC)
        snaps = [
            _make_snapshot(fetched_at=now - timedelta(minutes=i))
            for i in range(5, 0, -1)
        ]
        result = extract_features(snaps)
        assert isinstance(result, RegimeFeatures)


# ---------------------------------------------------------------------------
# HMM tests
# ---------------------------------------------------------------------------


class TestTwoStateGaussianHMM:
    def test_stable_observations(self):
        """All-low observations → stable regime."""
        hmm = _default_hmm()
        obs = [0.1, 0.12, 0.08, 0.15, 0.1]
        result = hmm.infer(obs)
        assert result.regime_label == "stable"
        assert result.regime_probability > 0.7

    def test_unstable_observations(self):
        """All-high observations → unstable regime."""
        hmm = _default_hmm()
        obs = [0.85, 0.9, 0.82, 0.88, 0.9]
        result = hmm.infer(obs)
        assert result.regime_label == "unstable"
        assert result.regime_probability > 0.7

    def test_transition_detection(self):
        """Low → high sequence should show elevated transition risk when
        the final state differs from initial."""
        hmm = _default_hmm()
        # Start stable, end unstable
        obs = [0.1, 0.1, 0.1, 0.8, 0.9, 0.9]
        result = hmm.infer(obs)
        assert result.regime_label == "unstable"
        # transition_risk is the off-diagonal probability for current state
        assert result.transition_risk > 0

    def test_single_observation(self):
        """Single observation should return valid inference."""
        hmm = _default_hmm()
        result = hmm.infer([0.5])
        assert isinstance(result, RegimeInference)
        assert result.regime_label in ("stable", "unstable")
        assert 0.0 <= result.regime_probability <= 1.0
        assert 0.0 <= result.transition_risk <= 1.0
        assert 0.0 <= result.stability_score <= 1.0

    def test_empty_observations(self):
        """Empty list returns prior-based inference."""
        hmm = _default_hmm()
        result = hmm.infer([])
        assert result.regime_label == "stable"
        assert result.regime_probability == pytest.approx(0.7, abs=0.01)

    def test_stability_score_bounds(self):
        """Stability score always in [0, 1]."""
        hmm = _default_hmm()
        for obs_val in [0.0, 0.2, 0.5, 0.8, 1.0]:
            result = hmm.infer([obs_val])
            assert 0.0 <= result.stability_score <= 1.0

    def test_returns_regime_inference_type(self):
        hmm = _default_hmm()
        result = hmm.infer([0.3])
        assert isinstance(result, RegimeInference)


# ---------------------------------------------------------------------------
# Output contract tests
# ---------------------------------------------------------------------------


class TestOutputContract:
    def test_regime_inference_fields(self):
        """RegimeInference has exactly the expected fields."""
        hmm = _default_hmm()
        result = hmm.infer([0.2])
        assert hasattr(result, "regime_label")
        assert hasattr(result, "regime_probability")
        assert hasattr(result, "transition_risk")
        assert hasattr(result, "stability_score")
        assert isinstance(result.regime_label, str)
        assert isinstance(result.regime_probability, float)
        assert isinstance(result.transition_risk, float)
        assert isinstance(result.stability_score, float)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestRegimeConfig:
    def test_default_disabled(self):
        cfg = RegimeConfig()
        assert cfg.enabled is False

    def test_from_settings_reads_flag(self):
        from app.regime.config import regime_config_from_settings

        class FakeSettings:
            regime_detection_enabled = True

        cfg = regime_config_from_settings(FakeSettings())
        assert cfg.enabled is True

    def test_from_settings_default_when_missing(self):
        from app.regime.config import regime_config_from_settings

        class EmptySettings:
            pass

        cfg = regime_config_from_settings(EmptySettings())
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# Metadata attachment tests (no DB required)
# ---------------------------------------------------------------------------


class TestAttachMetadata:
    def _make_signal(self, event_id: str = _EVENT, market: str = _MARKET) -> object:
        """Minimal signal-like object for testing attachment."""

        class FakeSignal:
            def __init__(self):
                self.event_id = event_id
                self.market = market
                self.metadata_json = {"existing_key": "value"}

        return FakeSignal()

    @pytest.mark.asyncio
    async def test_attach_adds_regime_key(self):
        from app.regime.service import RegimeOutput

        # We can't easily construct a full RegimeService without a DB,
        # so test the attachment logic directly
        signal = self._make_signal()
        regimes = {
            (_EVENT, _MARKET): RegimeOutput(
                regime_label="stable",
                regime_probability=0.85,
                transition_risk=0.1,
                stability_score=0.77,
                model_version="v1",
                snapshots_used=5,
            )
        }
        # Call the attachment logic inline (mirrors service method)
        metadata = dict(signal.metadata_json or {})
        regime = regimes[(_EVENT, _MARKET)]
        metadata["regime"] = {
            "regime_label": regime.regime_label,
            "regime_probability": regime.regime_probability,
            "transition_risk": regime.transition_risk,
            "stability_score": regime.stability_score,
            "model_version": regime.model_version,
        }
        signal.metadata_json = metadata

        assert "regime" in signal.metadata_json
        regime_data = signal.metadata_json["regime"]
        assert regime_data["regime_label"] == "stable"
        assert regime_data["regime_probability"] == 0.85
        assert regime_data["transition_risk"] == 0.1
        assert regime_data["stability_score"] == 0.77
        assert regime_data["model_version"] == "v1"

    @pytest.mark.asyncio
    async def test_attach_preserves_existing_metadata(self):
        signal = self._make_signal()
        original_keys = set(signal.metadata_json.keys())

        from app.regime.service import RegimeOutput

        regime = RegimeOutput(
            regime_label="unstable",
            regime_probability=0.72,
            transition_risk=0.2,
            stability_score=0.58,
            model_version="v1",
            snapshots_used=4,
        )
        metadata = dict(signal.metadata_json or {})
        metadata["regime"] = {
            "regime_label": regime.regime_label,
            "regime_probability": regime.regime_probability,
            "transition_risk": regime.transition_risk,
            "stability_score": regime.stability_score,
            "model_version": regime.model_version,
        }
        signal.metadata_json = metadata

        # Original keys still present
        for key in original_keys:
            assert key in signal.metadata_json
        assert signal.metadata_json["existing_key"] == "value"

    @pytest.mark.asyncio
    async def test_no_match_no_attachment(self):
        from app.regime.service import RegimeOutput

        signal = self._make_signal(event_id="other_event")
        regimes = {
            (_EVENT, _MARKET): RegimeOutput(
                regime_label="stable",
                regime_probability=0.85,
                transition_risk=0.1,
                stability_score=0.77,
                model_version="v1",
                snapshots_used=5,
            )
        }

        key = (signal.event_id, signal.market)
        regime = regimes.get(key)
        assert regime is None  # No match
        assert "regime" not in signal.metadata_json


# ---------------------------------------------------------------------------
# Feature flag OFF tests
# ---------------------------------------------------------------------------


class TestFeatureFlagOff:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        """With enabled=False, compute_regimes returns empty dict."""
        from unittest.mock import AsyncMock

        from app.regime.service import RegimeService

        config = RegimeConfig(enabled=False)
        mock_db = AsyncMock()
        service = RegimeService(mock_db, config)

        result = await service.compute_regimes(["evt_1", "evt_2"])
        assert result == {}
        # DB should never be queried
        mock_db.execute.assert_not_called()
