from aiida.engine import WorkChain
from aiida.orm import Int


class AddAndMultiplyWorkChain(WorkChain):
    def submit_sub_workchain(self):
        self.submit(AddAndMultiplyWorkChain, a=Int(1), b=Int(2), c=Int(3))
