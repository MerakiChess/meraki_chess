from future import annotations
from typing import Optional
import time

class TimeManager:
def init(self)->None:
self.start_ns=0; self.budget_ms:Optional=None
def start(self,budget_ms:Optional)->None:
self.start_ns=time.time_ns(); self.budget_ms=budget_ms
def time_up(self)->bool:
if self.budget_ms is None: return False
return (time.time_ns()-self.start_ns)/1e6 >= self.budget_ms