"""Lightweight 2-state Gaussian Hidden Markov Model (pure Python)."""

from __future__ import annotations

import math
from dataclasses import dataclass

STATES = ("stable", "unstable")
_STABLE = 0
_UNSTABLE = 1
_EPS = 1e-300  # floor to prevent log-domain underflow


@dataclass(frozen=True)
class RegimeInference:
    """Result of HMM inference at the final observation."""

    regime_label: str
    regime_probability: float
    transition_risk: float
    stability_score: float


class TwoStateGaussianHMM:
    """2-state HMM with univariate Gaussian emissions.

    Parameters are pre-set (not learned from data).  The forward algorithm
    computes exact posteriors in O(T) time with no external dependencies.
    """

    def __init__(
        self,
        stable_mean: float,
        stable_var: float,
        unstable_mean: float,
        unstable_var: float,
        p_stable_to_unstable: float,
        p_unstable_to_stable: float,
        initial_stable_prob: float,
    ) -> None:
        self._emission_mean = (stable_mean, unstable_mean)
        self._emission_var = (
            max(stable_var, _EPS),
            max(unstable_var, _EPS),
        )
        # Transition matrix: trans[i][j] = P(state_j | state_i)
        self._trans = (
            (1.0 - p_stable_to_unstable, p_stable_to_unstable),
            (p_unstable_to_stable, 1.0 - p_unstable_to_stable),
        )
        self._initial = (initial_stable_prob, 1.0 - initial_stable_prob)

    # ------------------------------------------------------------------
    def _gaussian_pdf(self, x: float, state: int) -> float:
        mean = self._emission_mean[state]
        var = self._emission_var[state]
        coeff = 1.0 / math.sqrt(2.0 * math.pi * var)
        exponent = -0.5 * ((x - mean) ** 2) / var
        return max(coeff * math.exp(exponent), _EPS)

    # ------------------------------------------------------------------
    def infer(self, observations: list[float]) -> RegimeInference:
        """Run the forward algorithm and return regime inference for the
        final time step.

        *observations* is a list of composite feature values (each in [0, 1]).
        At least one observation is required.
        """
        if not observations:
            return RegimeInference(
                regime_label="stable",
                regime_probability=self._initial[_STABLE],
                transition_risk=self._trans[_STABLE][_UNSTABLE],
                stability_score=self._initial[_STABLE],
            )

        # Initialise forward variable α_0
        alpha = [
            self._initial[s] * self._gaussian_pdf(observations[0], s)
            for s in (_STABLE, _UNSTABLE)
        ]
        alpha = self._normalise(alpha)

        # Forward pass
        for t in range(1, len(observations)):
            obs = observations[t]
            new_alpha = [0.0, 0.0]
            for j in (_STABLE, _UNSTABLE):
                total = sum(alpha[i] * self._trans[i][j] for i in (_STABLE, _UNSTABLE))
                new_alpha[j] = total * self._gaussian_pdf(obs, j)
            alpha = self._normalise(new_alpha)

        # Posterior at final step
        p_stable = alpha[_STABLE]
        p_unstable = alpha[_UNSTABLE]

        if p_stable >= p_unstable:
            label = "stable"
            prob = p_stable
            # Transition risk: weighted probability of switching away
            tr = self._trans[_STABLE][_UNSTABLE]
        else:
            label = "unstable"
            prob = p_unstable
            tr = self._trans[_UNSTABLE][_STABLE]

        # Stability score: how entrenched the regime is.
        # High posterior * low transition risk → high stability.
        stability = prob * (1.0 - tr)
        stability = max(0.0, min(1.0, stability))

        return RegimeInference(
            regime_label=label,
            regime_probability=round(prob, 6),
            transition_risk=round(tr, 6),
            stability_score=round(stability, 6),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _normalise(alpha: list[float]) -> list[float]:
        total = sum(alpha)
        if total <= 0:
            return [0.5, 0.5]
        return [a / total for a in alpha]
