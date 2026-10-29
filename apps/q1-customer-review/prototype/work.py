"""Cooperative, per-worker cancellation and work budgets; no global job state."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

MAX_WORK_STEPS=10_000_000
STAGE_SECONDS=60
CALCULATION_SECONDS=45
_current=ContextVar('q1_work_control',default=None)

class WorkCancelled(ValueError):pass
class WorkLimit(ValueError):pass

class WorkControl:
    def __init__(self,cancelled,*,seconds=STAGE_SECONDS,max_steps=MAX_WORK_STEPS,clock=time.monotonic):
        self.cancelled=cancelled;self.clock=clock;self.deadline=clock()+seconds;self.steps=0;self.max_steps=max_steps
    def check(self,steps=1):
        if self.cancelled():raise WorkCancelled('Upload cancelled')
        self.steps+=steps
        if self.steps>self.max_steps or self.clock()>=self.deadline:
            raise WorkLimit('Upload calculation exceeded its time or work budget. Current data was kept.')
    def calculation(self):
        self.deadline=min(self.deadline,self.clock()+CALCULATION_SECONDS);self.check()

def checkpoint(steps=1):
    control=_current.get()
    if control is not None:control.check(steps)

@contextmanager
def work_scope(control):
    token=_current.set(control)
    try:
        control.check();yield
    finally:_current.reset(token)
