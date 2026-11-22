"""Fresh camera feedback selects breakaway power without extending pulses."""
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from control.vision_approach_test import TurnFeedback


def check():
    for profiles in (False,True):
        feedback=TurnFeedback()
        plan=dict(heading_error_deg=8,normal_turn_clear=True)
        assert not feedback.use_normal_step('left',plan,profiles=profiles)
        for i in range(2):
            feedback.sent('left',0,i+1)
            assert not feedback.observe(0,i+.99)  # frame before pulse ended
            assert not feedback.observe(math.radians(.2),i+1.1)
        assert feedback.use_normal_step('left',plan,profiles=profiles)
        assert not feedback.use_normal_step('left',{**plan,'normal_turn_clear':False},profiles=profiles)
        assert not feedback.use_normal_step('right',plan,profiles=profiles)
        feedback.sent('left',0,3)
        feedback.observe(math.radians(4),3.1)
        assert not feedback.use_normal_step('left',plan,profiles=profiles)
        feedback.sent('left',0,4)
        feedback.observe(0,5)  # stale evidence must not request more power
        assert feedback.stalled_count==0
        feedback.reset()
        assert feedback.reference is None and feedback.stalled_count==0
    feedback=TurnFeedback()
    plan=dict(heading_error_deg=80,normal_turn_clear=True)
    assert feedback.use_normal_step('right',plan,profiles=False)
    assert not feedback.use_normal_step('right',plan,profiles=True)
    # Correct signs across +/- pi, and swap mapping only after two clear
    # opposite responses; stalling is never mistaken for reversed wiring.
    for i in range(2):
        feedback.sent('left',math.radians(179),i+1)
        assert not feedback.observe(math.radians(-177),i+1.1)
    assert not feedback.inverted
    for i in range(2):
        feedback.sent('left',0,i+3)
        corrected=feedback.observe(math.radians(-4),i+3.1)
        assert corrected==(i==1)
    assert feedback.inverted
    print('PASS: small-angle stall boost, sweep limit, recovery, stale frames, reset, turn signs')


if __name__=='__main__':
    check()
