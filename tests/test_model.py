import numpy as np
import pandas as pd
import pytest

from asset_risk.model import beta_parameters, integrate_eal, monte_carlo_event_loss


def test_beta_parameters_preserve_mean():
    alpha, beta = beta_parameters(0.25, 20)
    assert alpha / (alpha + beta) == pytest.approx(0.25)


def test_integrate_eal_matches_documented_anchors():
    aep = np.array([0.01, 0.02, 0.05, 0.20])
    loss = np.array([100.0, 80.0, 40.0, 10.0])
    expected = np.trapezoid([100, 100, 80, 40, 10, 0], [0, 0.01, 0.02, 0.05, 0.20, 1])
    assert integrate_eal(aep, loss) == pytest.approx(expected)


def test_mitigation_reduces_loss_with_identical_seed():
    assets = pd.DataFrame({"replacement_value_nzd": [1_000_000, 2_000_000]})
    common = dict(
        exposed_assets=assets,
        damage_mean=0.4,
        damage_concentration=20,
        iterations=250,
        value_sigma=0.2,
        systematic_sigma=0.1,
    )
    untreated = monte_carlo_event_loss(
        **common, mitigation_factor=1.0, rng=np.random.default_rng(7)
    )
    treated = monte_carlo_event_loss(
        **common, mitigation_factor=0.65, rng=np.random.default_rng(7)
    )
    assert np.allclose(treated, untreated * 0.65)


def test_invalid_aep_fails_loudly():
    with pytest.raises(ValueError):
        integrate_eal(np.array([0.01, 0.01]), np.array([100.0, 90.0]))

