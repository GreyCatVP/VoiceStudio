"""VoxCPM2 stop is held back a patch so the last syllable is not cut."""
import pytest

from engines.voxcpm2_subprocess.main import TailDelay, install_tail_patch


def test_tail_delay_holds_only_the_first_stops():
    d = TailDelay(1)
    assert d.hold(False) is False
    assert d.hold(True) is True      # first stop: one more patch
    assert d.hold(True) is False     # second stop: really stop
    d.reset()
    assert d.hold(True) is True      # next generation starts fresh


def test_zero_extra_changes_nothing():
    d = TailDelay(0)
    assert d.hold(True) is False


def test_model_without_stop_head_is_left_alone():
    class Bare:
        pass

    assert install_tail_patch(Bare(), 1) is None


def test_stop_head_wrapper_flips_only_the_held_stop():
    torch = pytest.importorskip("torch")

    class Model:
        pass

    m = Model()
    m.stop_head = torch.nn.Identity()
    delay = install_tail_patch(m, 1)
    assert delay is not None
    stop = torch.tensor([[0.0, 5.0]])
    go = torch.tensor([[5.0, 0.0]])
    assert m.stop_head(go).argmax(-1).item() == 0
    assert m.stop_head(stop).argmax(-1).item() == 0   # held once
    assert m.stop_head(stop).argmax(-1).item() == 1   # then it stops
    delay.reset()
    assert m.stop_head(stop).argmax(-1).item() == 0
