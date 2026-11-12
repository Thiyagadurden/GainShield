import numpy as np

from gainshield.controllers.baseline import baseline_gains
from gainshield.optimizer.gp import GPModel
from gainshield.optimizer.safe_bo import SafeBayesOpt


def test_zero_prior_margin_gp_is_unsafe_far_from_data():
    gp = GPModel(2, prior_mean=0.0, amplitude=0.6, ls_init=np.array([0.15, 0.15]), optimize=False)
    gp.fit(np.array([[0.5, 0.5]]), np.array([0.7]))
    mu, sd = gp.predict(np.array([[0.5, 0.5], [0.95, 0.05]]))
    assert mu[0] - 2 * sd[0] > 0.15
    assert mu[1] - 2 * sd[1] < 0.15


def test_safe_set_starts_at_seed_and_grows(cfg, cert):
    bo = SafeBayesOpt(cfg, cert, baseline_gains(cfg))
    z = np.ones(5) * np.array([1, 1, 0.33, 1, 1])
    S0 = bo.safe_mask(bo.predict(z))
    assert S0.sum() == 1 and S0[bo.seed_index]
    bo.add_observation(baseline_gains(cfg), z, 1.0, 0.7, 0.6)
    S1 = bo.safe_mask(bo.predict(z))
    assert S1.sum() > 1


def test_proposals_stay_in_candidate_set(cfg, cert):
    bo = SafeBayesOpt(cfg, cert, baseline_gains(cfg))
    z = np.array([1, 1, 0.33, 1, 1.0])
    bo.add_observation(baseline_gains(cfg), z, 1.0, 0.7, 0.6)
    for _ in range(3):
        p = bo.propose(z)
        assert any(np.allclose([p.gains.Kp, p.gains.Ki], g) for g in bo.cand_gains)
        bo.add_observation(p.gains, z, 0.9, 0.65, 0.6)
