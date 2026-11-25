import json

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from swarmtrace.cli import main
from swarmtrace.detect.assignment import AssignmentLogistic, _loss
from swarmtrace.eval.assignment_review import review_assignments
from swarmtrace.eval.read_attribution import _challenge_engine
from swarmtrace.features.assignment import ASSIGNMENT_COLUMNS
from swarmtrace.trace.authorization import write_authorization
from swarmtrace.trace.context import Context, ContextLevel, HandoffScope, write_context


def test_pooled_run_loss_gradient_and_exact_max_scoring():
    features = np.array([[0., 1.], [4., 0.], [0., 3.], [2., 1.], [1., 2.]])
    sizes = np.array([2, 1, 2])
    labels = np.array([1., 0., 1.])
    starts = np.array([0, 2, 3])
    params = np.array([0.3, -0.7, -0.2])
    numerical = [(_loss(params + d, features, labels, sizes, starts)[0]
                  - _loss(params - d, features, labels, sizes, starts)[0]) / 2e-5 for d in np.eye(3) * 1e-5]
    np.testing.assert_allclose(_loss(params, features, labels, sizes, starts)[1], numerical, atol=1e-8)
    model = AssignmentLogistic(np.zeros(2), np.ones(2), np.ones(2), -1.)
    bag = np.array([[3., 0.], [0., 4.]])
    assert model.score(bag) == model.score(bag[::-1]) == model.score(bag[[1]])
    assert model.score(bag) < model.score(bag.max(axis=0, keepdims=True))
    assert model.score(bag[:0]) == 0.


def test_signed_contribution_ablation_differs_only_if_best_evidence_is_split():
    model = AssignmentLogistic(np.zeros(2), np.ones(2), np.array([1., -1.]), 0.)
    together = np.array([[3., 1.], [2., 2.]])
    split = np.array([[3., 2.], [2., 1.]])
    assert model.pooled_evidence_score(together) == model.score(together) == model.pooled_evidence_score(split)
    assert model.score(split) < model.pooled_evidence_score(split)
    one = AssignmentLogistic(np.zeros(1), np.ones(1), np.array([-1.]), 0.)
    assert one.score(together[:, :1]) == one.pooled_evidence_score(together[:, :1])
    assert one.pooled_evidence_score(np.empty((0, 1))) == 0.


def test_one_grant_matches_logistic_and_duplicate_whole_bag_keeps_run_weight():
    inputs = np.array([[0., 0.], [0., 2.], [1., 0.], [0., 0.], [2., 1.], [2., 2.]])
    labels = np.array([False, False, True, False, True, True])
    bags = [r[None, :] for r in inputs]
    model = AssignmentLogistic.fit(bags, labels)
    ref = LogisticRegression(tol=1e-12).fit((inputs - inputs.mean(0)) / inputs.std(0), labels)
    np.testing.assert_allclose(model.weights, ref.coef_[0], atol=2e-5)
    enlarged = list(bags)
    enlarged[2] = np.tile(enlarged[2], (5, 1))
    repeated = AssignmentLogistic.fit([*enlarged, np.empty((0, 2))], np.append(labels, True))
    np.testing.assert_allclose(model.weights, repeated.weights, atol=1e-8)
    assert model.intercept == pytest.approx(repeated.intercept)
    with pytest.raises(ValueError, match="both classes"):
        AssignmentLogistic.fit([bags[0], bags[0][:0]], [False, True])
    with pytest.raises(ValueError, match="matching columns"):
        AssignmentLogistic.fit([bags[0], np.ones((1, 3))], [False, True])


def test_review_cli_without_labels_with_missing_partial_and_scored_capture(tmp_path, capsys):
    engine, grants = _challenge_engine()
    engine.run(18, tmp_path / "trace.jsonl")
    context = Context(engine.read_audit.run_id, ContextLevel.C2, {},
                      tuple(HandoffScope(g.sender, g.receiver, g.host, g.files) for g in grants))
    write_context(tmp_path / "context.json", context)
    main(["review-assignments", "--run", str(tmp_path)])
    missing = json.loads(capsys.readouterr().out)
    assert missing['assignments'] == [] and not missing['capture_present']
    assert missing['missing_decisions'] == missing['successful_reads'] > 0
    write_authorization(tmp_path / "authorization.json", engine.read_audit)
    protocol = {"candidate": "assignment-logistic", "assignment_columns": list(ASSIGNMENT_COLUMNS),
                "model": {"center": [0.] * 5, "scale": [1.] * 5, "weights": [1.] * 5, "intercept": -2.}}
    (tmp_path / "protocol.json").write_text(json.dumps(protocol))
    report = review_assignments(tmp_path, tmp_path)
    assert report['unknown_reads'] > 0 and report['assignments'][0]['review_score'] == report['max_observed_score']
    assert 'threshold' not in report and report['missing_decisions'] == 0
    protocol['model']['scale'][2] = 0
    (tmp_path / "protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="scales"):
        review_assignments(tmp_path, tmp_path)
