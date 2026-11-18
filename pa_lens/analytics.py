"""Causal local indicators, not provider replicas or trade signals."""
class LocalIndicators:
    def __init__(self):
        self.bars=0
        self.ema=self.previous=self.gain=self.loss=None
        self.gains=self.losses=0.

    def update(self,bar):
        close=bar.close
        self.bars+=1
        self.ema=close if self.ema is None else self.ema+2/21*(close-self.ema)
        if self.previous is not None:
            delta=close-self.previous
            gain,loss=max(delta,0),max(-delta,0)
            if self.bars<=15:
                self.gains+=gain; self.losses+=loss
                if self.bars==15:
                    self.gain,self.loss=self.gains/14,self.losses/14
            else:
                self.gain=(13*self.gain+gain)/14
                self.loss=(13*self.loss+loss)/14
        self.previous=close

    def snapshot(self):
        rsi=None
        if self.gain is not None:
            total=self.gain+self.loss
            rsi=100*self.gain/total if total else 50.
        return {"origin":"local_closed_bar_calculation","bars":self.bars,
                "ema20":{"value":self.ema,"ready":self.bars>=20,"seed":"first_close","warmup_bars":20},
                "rsi14":{"value":rsi,"ready":self.bars>=15,"seed":"mean_first_14_deltas_then_wilder","warmup_bars":15,"flat_value":50}}
